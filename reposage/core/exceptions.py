"""Exception hierarchy for RepoSage core.

Routes catch these at the API boundary and map them to HTTP responses.
Core code never raises bare `Exception` — it raises one of these.
"""


class RepoSageError(Exception):
    """Base for all RepoSage-raised errors."""


# --- Ingestion ---------------------------------------------------------------

class IngestionError(RepoSageError):
    """Anything that goes wrong during the ingestion pipeline."""


class InvalidRepoURLError(IngestionError):
    """The provided GitHub URL could not be parsed."""


class RepoTooLargeError(IngestionError):
    """The repo exceeds REPOSAGE_MAX_REPO_SIZE_MB."""


class RepoCloneError(IngestionError):
    """Clone failed (network, auth, missing branch, etc.)."""


# --- Chunking ----------------------------------------------------------------

class ChunkingError(RepoSageError):
    """Tree-sitter parse failed or chunker produced invalid output."""


# --- Embedding ---------------------------------------------------------------

class EmbeddingError(RepoSageError):
    """Embedder failed to produce vectors."""


# --- Vector store ------------------------------------------------------------

class VectorStoreError(RepoSageError):
    """Underlying vector DB call failed."""


class CollectionNotFoundError(VectorStoreError):
    """Asked for a collection that doesn't exist."""


# --- Retrieval & synthesis ---------------------------------------------------

class RetrievalError(RepoSageError):
    """Vector search or rerank failed."""


class SynthesisError(RepoSageError):
    """Claude API call failed or returned an unusable answer."""
