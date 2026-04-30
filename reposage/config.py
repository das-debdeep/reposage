from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REPOSAGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    github_token: SecretStr
    anthropic_api_key: SecretStr

    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_persist_dir: Path = Path("./data/chroma")

    embedding_model: str = "nomic-ai/nomic-embed-text-v1.5"
    embedding_device: Literal["cpu", "cuda", "mps"] = "cpu"

    retrieval_top_k: int = Field(default=20, ge=1, le=100)
    rerank_top_n: int = Field(default=5, ge=1, le=20)
    similarity_threshold: float = Field(default=0.3, ge=0.0, le=1.0)

    claude_model: str = "claude-opus-4-7"
    claude_max_tokens: int = Field(default=2048, ge=1, le=8192)

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    max_repo_size_mb: int = Field(default=500, ge=1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
