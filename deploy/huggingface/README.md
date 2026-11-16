---
title: RepoSage
emoji: 📚
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# RepoSage

Ask questions about a public GitHub repository and get answers that cite the
files they came from.

This Space runs the Gradio front-end on top of the same RepoSage service layer
as the FastAPI app: prompt-injection filtering, hybrid retrieval (vector +
keyword search), reranking, answer verification and per-request
latency/token/cost accounting.

## Postgres inside the Space

The container starts an embedded PostgreSQL 16 server with the `pgvector`
extension (`pgserver` pip wheel) on first use, so there is no external database
to provision. Data lives at `/data/pgdata`.

- Free CPU Basic disk is **ephemeral**: the index is lost on restart. Attach a
  Storage Bucket at `/data` to keep it, or just re-index (one click).
- Docker Spaces require a paid plan (PRO/Team/Enterprise). On a free account,
  use the Gradio SDK bundle instead (`README.gradio.md`).

## Add the Gemini API key

Space → **Settings → Variables and secrets → New secret**:

| Name | Value |
| --- | --- |
| `GEMINI_API_KEY` | your key from https://aistudio.google.com/apikey |

It is injected as an environment variable at runtime and never appears in the
image or the repository.

Optional variables: `CHAT_MODEL` (default `gemini-3.5-flash-lite`),
`CHAT_FALLBACK_MODELS` (default `gemini-3.1-flash-lite`),
`EMBEDDING_MODEL` (`gemini-embedding-001`), `EMBEDDING_DIM` (`768`),
`MAX_CHUNKS` (`800`), `RERANKER` (`heuristic` or `gemini`),
`GITHUB_TOKEN` (private repositories).
