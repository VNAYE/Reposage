---
title: RepoSage
emoji: 📚
colorFrom: indigo
colorTo: purple
sdk: gradio
app_file: app.py
python_version: "3.12"
pinned: false
---

# RepoSage

Ask questions about a public GitHub repository and get answers that cite the
files they came from.

This is the **free-tier** bundle: a Gradio SDK Space. The same RepoSage service
layer runs here (guardrails, hybrid retrieval, reranking, verification,
latency/token/cost accounting), and PostgreSQL + pgvector are started inside the
Python process tree by the `pgserver` wheel. No Docker, no external database.

## Why Gradio SDK

As of 2026, Hugging Face requires a paid plan to create Docker Spaces; free
personal accounts in good standing can host up to 2 Gradio Spaces on ZeroGPU.
This bundle targets that path. CPU Basic hardware is 2 vCPU / 16 GB RAM with a
50 GB **ephemeral** disk, so the index is rebuilt after a restart. Gradio SDK
Spaces have no `/data` volume; the embedded database lives under the home
directory and is wiped on restart. Re-index (one click) after a restart, or use
the Docker bundle with a Storage Bucket for durability.

## Add the Gemini API key

Space → **Settings → Variables and secrets → New secret**:

| Name | Value |
| --- | --- |
| `GEMINI_API_KEY` | your key from https://aistudio.google.com/apikey |

Optional: `CHAT_MODEL`, `CHAT_FALLBACK_MODELS`, `EMBEDDING_MODEL`,
`EMBEDDING_DIM`, `MAX_CHUNKS` (start with 40-80 on a free key), `RERANKER`,
`GITHUB_TOKEN`.

Free-tier Gemini keys allow roughly 15 generate-content requests per minute per
model; `CHAT_FALLBACK_MODELS` (default `gemini-3.1-flash-lite`) covers `429` and
`503` spikes.

Outbound traffic on Spaces is limited to ports 80/443/8080; the Gemini and
GitHub APIs both use 443, so no extra configuration is needed.
