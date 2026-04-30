"""Fetch a GitHub repository at a specific commit and yield its source files.

Strategy: shallow `git clone --depth=1` into a temp directory, walk the working
tree, apply filter rules, and yield (relative_path, content, language) tuples.
The clone is removed when the loader's context manager exits.

We use `gitpython` rather than the GitHub Tree API because:
  - One network round-trip vs. recursive API calls (which rate-limit at 5000/hr).
  - File contents are read from local disk — no per-file API request.
  - Works the same way for forks and private repos given a token.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from git import GitCommandError, Repo

from reposage.config import Settings
from reposage.core.exceptions import (
    InvalidRepoURLError,
    RepoCloneError,
    RepoTooLargeError,
)
from reposage.ingestion.filters import classify_file
from reposage.models.schemas import Language, RepoRef

_GITHUB_URL_RE = re.compile(
    r"""^
    (?:https?://github\.com/|git@github\.com:)
    (?P<owner>[A-Za-z0-9_.\-]+)
    /
    (?P<repo>[A-Za-z0-9_.\-]+?)
    (?:\.git)?
    /?
    $""",
    re.VERBOSE,
)


@dataclass(frozen=True)
class LoadedFile:
    """A single file that passed the filters and is ready to be chunked."""
    rel_path: Path
    content: str
    language: Language


def parse_github_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL.

    Accepts both HTTPS and SSH forms, with or without the `.git` suffix.
    """
    match = _GITHUB_URL_RE.match(url.strip())
    if match is None:
        raise InvalidRepoURLError(f"Not a recognized GitHub URL: {url!r}")
    return match["owner"], match["repo"]


class GitHubLoader:
    """Clones a repo to a temp dir and walks its files.

    Use as an async context manager — the temp clone is cleaned up on exit.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._token = settings.github_token.get_secret_value()
        self._max_bytes = settings.max_repo_size_mb * 1024 * 1024

    @asynccontextmanager
    async def clone(
        self,
        repo_url: str,
        branch: str | None = None,
    ) -> AsyncIterator[tuple[RepoRef, Path]]:
        """Clone a repo to a temp dir; yield (RepoRef, clone_path).

        The clone is shallow (`--depth=1`) on the requested branch, or the
        repo's default branch if `branch` is None.
        """
        owner, repo_name = parse_github_url(repo_url)
        tmp_root = Path(tempfile.mkdtemp(prefix="reposage-"))
        clone_path = tmp_root / repo_name

        try:
            repo = await asyncio.to_thread(
                self._clone_blocking, repo_url, clone_path, branch
            )
            commit_sha = repo.head.commit.hexsha

            await asyncio.to_thread(self._enforce_size_limit, clone_path)

            ref = RepoRef(owner=owner, repo=repo_name, commit_sha=commit_sha)
            yield ref, clone_path
        finally:
            await asyncio.to_thread(shutil.rmtree, tmp_root, True)

    async def walk_files(self, clone_path: Path) -> AsyncIterator[LoadedFile]:
        """Yield every file in the clone that passes the filters."""
        # Collect paths off-thread (stat() is blocking), then read each file
        # off-thread as well. Yielding back into the async iterator happens
        # on the event loop thread.
        candidates = await asyncio.to_thread(self._collect_candidates, clone_path)
        for rel_path, abs_path, language in candidates:
            try:
                content = await asyncio.to_thread(_read_text_safe, abs_path)
            except OSError:
                continue  # unreadable — skip silently, don't fail the whole job
            if content is None:
                continue
            yield LoadedFile(rel_path=rel_path, content=content, language=language)

    # ------------------------------------------------------------------ #
    # Blocking helpers — only called via asyncio.to_thread.
    # ------------------------------------------------------------------ #

    def _clone_blocking(
        self,
        repo_url: str,
        target: Path,
        branch: str | None,
    ) -> Repo:
        # Inject the PAT into HTTPS URLs so private repos work.
        # Format: https://<token>@github.com/owner/repo
        auth_url = re.sub(
            r"^https://github\.com/",
            f"https://{self._token}@github.com/",
            repo_url,
        )
        try:
            kwargs: dict = {"depth": 1, "single_branch": True}
            if branch is not None:
                kwargs["branch"] = branch
            return Repo.clone_from(auth_url, str(target), **kwargs)
        except GitCommandError as e:
            raise RepoCloneError(f"git clone failed: {e.stderr or e}") from e

    def _enforce_size_limit(self, clone_path: Path) -> None:
        total = 0
        for path in clone_path.rglob("*"):
            if path.is_file() and ".git" not in path.parts:
                total += path.stat().st_size
                if total > self._max_bytes:
                    raise RepoTooLargeError(
                        f"Repo exceeds {self._settings.max_repo_size_mb} MB cap "
                        f"(got at least {total / 1_048_576:.1f} MB)"
                    )

    def _collect_candidates(
        self, clone_path: Path
    ) -> list[tuple[Path, Path, Language]]:
        out: list[tuple[Path, Path, Language]] = []
        for abs_path in clone_path.rglob("*"):
            if not abs_path.is_file():
                continue
            rel_path = abs_path.relative_to(clone_path)
            try:
                size = abs_path.stat().st_size
            except OSError:
                continue
            result = classify_file(rel_path, size)
            if result.included and result.language is not None:
                out.append((rel_path, abs_path, result.language))
        return out


def _read_text_safe(path: Path) -> str | None:
    """Read a file as UTF-8; return None if it's actually binary."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
