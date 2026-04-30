from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


# ---------------------------------------------------------------------------
# Repo identity
# ---------------------------------------------------------------------------

class RepoRef(BaseModel):
    """Stable identifier for an indexed repository at a specific commit."""

    model_config = ConfigDict(frozen=True)

    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)
    commit_sha: str = Field(min_length=7, max_length=40)

    @property
    def collection_name(self) -> str:
        # Format: owner__repo@commit_sha — matches CLAUDE.md naming rule.
        return f"{self.owner}__{self.repo}@{self.commit_sha}"

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


# ---------------------------------------------------------------------------
# Chunks
# ---------------------------------------------------------------------------

ChunkType = Literal["class", "function", "method", "block", "prose", "config"]
Language = Literal[
    "python", "typescript", "javascript", "go", "rust", "java",
    "cpp", "c", "ruby", "markdown", "rst", "yaml", "toml", "json", "dockerfile", "other",
]


class ChunkMetadata(BaseModel):
    """Filterable metadata stored alongside the embedding in the vector store.

    Anything we want to filter, cite, or show in the UI lives here.
    Anything we embed lives in Chunk.text.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str
    language: Language
    chunk_type: ChunkType
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol_name: str | None = None  # e.g. "MyClass.my_method" for code chunks

    @field_validator("end_line")
    @classmethod
    def end_after_start(cls, v: int, info) -> int:
        start = info.data.get("start_line")
        if start is not None and v < start:
            raise ValueError("end_line must be >= start_line")
        return v


class Chunk(BaseModel):
    """A single embedded unit. Text is what the embedder sees;
    metadata is what we filter and cite by."""

    model_config = ConfigDict(frozen=True)

    id: str  # deterministic — see ingestion pipeline for derivation
    text: str = Field(min_length=1)
    metadata: ChunkMetadata
    token_count: int | None = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# Ingestion job lifecycle
# ---------------------------------------------------------------------------

class JobState(str, Enum):
    PENDING = "pending"
    CLONING = "cloning"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    STORING = "storing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobProgress(BaseModel):
    files_total: int = 0
    files_processed: int = 0
    chunks_total: int = 0
    chunks_embedded: int = 0


class IngestJob(BaseModel):
    job_id: UUID = Field(default_factory=uuid4)
    repo_url: HttpUrl
    repo: RepoRef | None = None  # populated once we resolve the commit
    state: JobState = JobState.PENDING
    progress: JobProgress = Field(default_factory=JobProgress)
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# API contracts
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    repo_url: HttpUrl
    branch: str | None = None  # defaults to repo's default branch


class IngestResponse(BaseModel):
    job_id: UUID
    state: JobState


class JobStatusResponse(BaseModel):
    job_id: UUID
    state: JobState
    progress: JobProgress
    repo: RepoRef | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class RepoSummary(BaseModel):
    repo: RepoRef
    chunk_count: int
    indexed_at: datetime


class RepoListResponse(BaseModel):
    repos: list[RepoSummary]
