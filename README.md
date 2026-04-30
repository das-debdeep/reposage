# RepoSage

Ask natural language questions about any GitHub repository. Answers are grounded in the actual code, with file:line citations.

Built as a hand-rolled RAG pipeline (no LangChain) — see `CLAUDE.md` for architecture and design decisions.

## Status

Phase 1 — Scaffold + Ingestion Pipeline (in progress).

## Setup

```bash
uv sync
cp .env.example .env  # then fill in tokens
```
