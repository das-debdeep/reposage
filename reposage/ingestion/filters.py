"""File inclusion/exclusion rules for ingestion.

Rules are data, not code: include extensions and special filenames live in
frozen sets; exclusion patterns are matched as path segments. This keeps the
filtering logic trivial to read and unit-test.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reposage.models.schemas import Language

# Map of file extension → embedding-time language label.
# This is the single source of truth for "what counts as code we index."
EXTENSION_LANGUAGE: dict[str, Language] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".rb": "ruby",
    ".md": "markdown",
    ".rst": "rst",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".json": "json",
}

# Filenames (no extension or special-cased) that we always include.
INCLUDE_FILENAMES: dict[str, Language] = {
    "Dockerfile": "dockerfile",
    "Containerfile": "dockerfile",
    "pyproject.toml": "toml",
    "package.json": "json",
}

# Path segments that disqualify a file. Match if any segment of the relative
# path equals one of these — covers nested cases like `pkg/node_modules/...`.
EXCLUDED_DIR_SEGMENTS: frozenset[str] = frozenset({
    "node_modules", ".git", "dist", "build", "__pycache__",
    ".venv", "venv", ".tox", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "target",  # Rust build dir
    ".next", ".nuxt", "out",  # JS frameworks
    "vendor",  # Go / Ruby
})

# Suffix patterns we never want, even if the extension passed.
EXCLUDED_SUFFIXES: frozenset[str] = frozenset({
    ".lock", ".min.js", ".min.css", ".map",
    ".pyc", ".pyo", ".o", ".so", ".dylib", ".dll",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
})

# Maximum size of a single file we'll ingest. Larger files are nearly always
# generated, vendored, or data — embeddings of them are not useful.
MAX_FILE_BYTES: int = 500_000  # 500 KB


@dataclass(frozen=True)
class FilterResult:
    """Outcome of applying filters to a single file."""
    included: bool
    language: Language | None = None
    reason: str | None = None  # populated when excluded, for logging


def classify_file(rel_path: Path, size_bytes: int) -> FilterResult:
    """Decide whether a file should be ingested, and if so, label its language.

    Args:
        rel_path: path relative to the repo root.
        size_bytes: file size on disk.

    Returns:
        FilterResult.included=True with a language if the file qualifies;
        otherwise included=False with a human-readable reason.
    """
    # 1. Excluded directories anywhere in the path.
    for segment in rel_path.parts:
        if segment in EXCLUDED_DIR_SEGMENTS:
            return FilterResult(included=False, reason=f"in excluded dir: {segment}")

    # 2. Hidden files and dotfiles (other than known includes).
    if rel_path.name.startswith(".") and rel_path.name not in INCLUDE_FILENAMES:
        return FilterResult(included=False, reason="hidden file")

    # 3. Excluded suffixes (binaries, lockfiles, minified assets).
    name_lower = rel_path.name.lower()
    for suffix in EXCLUDED_SUFFIXES:
        if name_lower.endswith(suffix):
            return FilterResult(included=False, reason=f"excluded suffix: {suffix}")

    # 4. Size cap.
    if size_bytes > MAX_FILE_BYTES:
        return FilterResult(included=False, reason=f"too large: {size_bytes} bytes")

    # 5. Whole-filename includes (Dockerfile, pyproject.toml, ...).
    if rel_path.name in INCLUDE_FILENAMES:
        return FilterResult(included=True, language=INCLUDE_FILENAMES[rel_path.name])

    # 6. Extension-based includes.
    language = EXTENSION_LANGUAGE.get(rel_path.suffix.lower())
    if language is not None:
        return FilterResult(included=True, language=language)

    return FilterResult(included=False, reason=f"unknown extension: {rel_path.suffix}")
