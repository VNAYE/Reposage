# RepoSage

Ask questions about a GitHub repository and get answers that cite the exact
files and line ranges they came from.

**Live demo:** https://vnaye.github.io/Reposage-web/

RepoSage is a full RAG pipeline: it downloads a repo, chunks it, embeds it,
stores it in Postgres + pgvector, retrieves with hybrid search, reranks,
answers with Gemini, verifies the answer against the retrieved sources, and
records latency, tokens and cost for every request.

![stack](https://img.shields.io/badge/Python-3.12-3776AB) ![stack](https://img.shields.io/badge/FastAPI-0.163-009688) ![stack](https://img.shields.io/badge/React-19-61DAFB) ![stack](https://img.shields.io/badge/Postgres-pgvector-336791)

## What it does

| Capability | Where |
| --- | --- |
| Answers questions about a codebase | `generation/chat.py` |
| Cites the source file and line range for every claim | `generation/prompts.py`, `generation/verifier.py` |
| Hybrid retrieval (keyword + vector) with reranking | `retrieval/hybrid.py`, `retrieval/rerankers.py` |
| Retrieval + answer quality test set | `backend/eval/` |
| Answer verification against retrieved sources | `generation/verifier.py` |
| Prompt-injection filtering | `generation/guardrails.py` |
| Latency, token and cost tracking | `observability/metrics.py` |
| Streaming React chat UI | `frontend/` |
| Gradio chat for Hugging Face Spaces | `gradio_app/` |
| Docker Compose stack | `docker-compose.yml` |

## Architecture

```
                    ┌──────────────────────────────┐
  GitHub tarball ──▶│ GitHubLoader → CodeChunker   │
                    │ → GeminiEmbeddingProvider    │
                    └──────────────┬───────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │ PostgresIndex                │
                    │  chunks + pgvector (HNSW)    │
                    │  full-text search (tsvector) │
                    └──────────────┬───────────────┘
  question ──▶ Guardrail ──▶ HybridRetriever (RRF) ──▶ Reranker
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │ PromptBuilder → Gemini        │
                    │ → CitationVerifier           │
                    │ → LlmGroundednessVerifier    │
                    │ → MetricsRecorder            │
                    └──────────────┬───────────────┘
                                   ▼
                    SSE: sources → tokens → verification → done
                                   │
                    ┌──────────────┴───────────────┐
                    ▼                              ▼
              React chat UI                  Gradio Space
```

Every arrow is an interface in `backend/reposage/domain/interfaces.py`. The
container (`core/container.py`) is the only place that picks concrete classes.

## Quick start (Docker Compose)

Requires Docker with the Compose plugin.

```bash
cp .env.example .env          # then put your key in GEMINI_API_KEY
docker compose up --build
```

- React UI: http://localhost:8080
- FastAPI + OpenAPI: http://localhost:8000/docs
- Postgres + pgvector: localhost:5432 (internal network too)

Index a repository from the UI (owner/name + ref), wait for the job to finish,
then ask a question. `docker compose --profile demo up gradio` also starts the
Gradio UI on http://localhost:7860.

## Where to add the API key

| Environment | Where |
| --- | --- |
| Local backend / Compose | `.env` in the repo root: `GEMINI_API_KEY=...` |
| Hugging Face Space | Space → **Settings → Variables and secrets → New secret**, name `GEMINI_API_KEY` |
| CI / shell | export `GEMINI_API_KEY=...` before running tests or eval |

Get a key at <https://aistudio.google.com/apikey>. `.env` is gitignored; the key
is never baked into an image.

## Local development

Backend (Python 3.11+; Docker uses 3.12):

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp ../.env.example ../.env        # fill GEMINI_API_KEY
.venv/bin/uvicorn reposage.main:create_app --factory --reload
```

Index from the CLI:

```bash
.venv/bin/python -m scripts.ingest pallets/click --ref main
.venv/bin/python -m scripts.ingest demo --source local --ref eval/fixtures/demo_repo
```

Frontend:

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Provider + storage wiring |
| `POST` | `/api/repos` | Queue an index job (`{owner, name, ref}`) |
| `GET` | `/api/repos/jobs/{id}` | Job status + report |
| `GET` | `/api/repos` | Indexed repositories and chunk counts |
| `DELETE` | `/api/repos/{owner}/{name}` | Drop a repository index |
| `POST` | `/api/chat` | SSE stream (`{repo, question}`) |
| `GET` | `/api/metrics?hours=24` | Requests, tokens, cost, p95 latency |

SSE events: `sources`, `token`, `verification`, `done`, `error`. `done` carries
`usage` (tokens, cost, latency, model) and `citations` (path + line range).

## Hugging Face Spaces

Hugging Face's current rules matter:

- **Free tier**: CPU Basic is 2 vCPU / 16 GB RAM / 50 GB **ephemeral** disk. As of
  2026, creating a Docker Space requires a paid plan (PRO/Team/Enterprise); free
  personal accounts in good standing can host up to **2 Gradio Spaces on
  ZeroGPU**. Static Spaces are free but cannot run Python.
- **Outbound network** is limited to ports 80/443/8080. Gemini and GitHub use 443.
- **Secrets** are injected as environment variables at runtime.
- **Persistence**: attach a Storage Bucket at `/data` (paid, per-TB) or accept
  that the index is rebuilt after a restart.

Both bundles include PostgreSQL + pgvector **inside the app** via the
`pgserver` pip wheel, so there is no external database to provision.

### Free path — Gradio SDK Space

Hugging Face's only free compute path in 2026 is a Gradio Space on ZeroGPU
(free accounts in good standing can host up to 2). This bundle runs entirely on
the Space's CPU; ZeroGPU is simply the hardware it is scheduled on. If the
runtime rejects a Space with no `@spaces.GPU` handler, use the Docker bundle
with a PRO plan instead.

```bash
./scripts/package_hf_space.sh gradio
# -> dist/hf_space_gradio
```

One command creates/reuses the Space, adds the Gemini secret, uploads the bundle,
waits for the build and runs a live test:

```bash
backend/.venv/bin/python scripts/deploy_hf_space.py
```

The script picks `zero-a10g` on a free account and `cpu-basic` on PRO. If you
prefer the UI: create a Space (SDK **Gradio**, hardware **ZeroGPU**), upload
`dist/hf_space_gradio`, and add the `GEMINI_API_KEY` secret in Settings.

ZeroGPU requires at least one registered `@spaces.GPU` handler at startup; the
bundle includes a hidden one-second GPU ping and never uses the GPU for real work.

Gradio SDK Spaces have no `/data` volume, so the embedded database lives under
the home directory and is wiped on restart; re-index after a restart.

### Docker Space (paid plan)

```bash
./scripts/package_hf_space.sh docker
# -> dist/hf_space_docker
```

Create a Space with SDK **Docker**, upload the bundle, add `GEMINI_API_KEY`.
The container runs as UID 1000, starts Postgres on first use, stores data in
`/data/pgdata`, and serves Gradio on 7860.

`docker compose --profile demo up --build` runs the same image locally.

## Evaluation

```bash
cd backend
.venv/bin/python -m eval.run_eval                 # offline fakes, no key needed
.venv/bin/python -m eval.run_eval --provider gemini
.venv/bin/python -m eval.run_eval --retrieval-only --k 8 --min-recall 0.8
```

Reports recall@k, MRR, citation precision, answers produced and verified rate.
Exit code is 1 when recall is below `--min-recall`, so it can gate CI. The
bundled question set targets `eval/fixtures/demo_repo`; add your own questions
with `expected_paths`.

Offline mode uses deterministic fake providers: it validates the plumbing, not
Gemini's answer quality. Run with `--provider gemini` for a real measurement.

## Design: one task, one class

| Concern | Class | File |
| --- | --- | --- |
| Load a repo | `GitHubLoader`, `LocalDirectoryLoader` | `ingestion/loaders.py` |
| Split files | `CodeChunker` | `ingestion/chunker.py` |
| Orchestrate indexing | `RepositoryIndexer` | `ingestion/indexer.py` |
| Track index jobs | `IndexJobStore` | `ingestion/jobs.py` |
| Store + search | `PostgresIndex`, `LocalIndex` | `storage/` |
| Embed text | `GeminiEmbeddingProvider` | `providers/gemini.py` |
| Retrieve | `HybridRetriever` | `retrieval/hybrid.py` |
| Rerank | `HeuristicReranker`, `GeminiReranker` | `retrieval/rerankers.py` |
| Filter input | `PromptInjectionFilter` | `generation/guardrails.py` |
| Build prompts | `PromptBuilder` | `generation/prompts.py` |
| Answer | `ChatService` | `generation/chat.py` |
| Verify | `CitationVerifier`, `LlmGroundednessVerifier`, `CompositeVerifier` | `generation/verifier.py` |
| Price + record | `CostModel`, `MetricsRecorder` | `observability/metrics.py` |
| Wire it | `build_container` | `core/container.py` |

## Adding a capability (without editing existing classes)

Every extension point is a registry. Drop a file in the matching package, add a
decorator and a factory, and select it with an env var:

```python
# backend/reposage/providers/openai.py
from reposage.core.plugins import chat_providers

@chat_providers.register("openai")
def build(settings, deps):
    return OpenAIChatProvider(settings.openai_api_key)
```

Then `CHAT_PROVIDER=openai`. Autodiscovery imports every module in
`providers/`, `storage/`, `retrieval/`, `generation/`, `ingestion/`, so no
existing file changes.

Available registries: `chat_providers`, `embedding_providers`, `index_stores`,
`metrics_sinks`, `repo_loaders`, `chunkers`, `rerankers`, `guardrails`,
`verifiers`.

## Configuration

See `.env.example` for the full list. Highlights:

| Variable | Default | Notes |
| --- | --- | --- |
| `GEMINI_API_KEY` | — | required for Gemini providers |
| `CHAT_MODEL` | `gemini-3.5-flash-lite` | switch to `gemini-3.7-flash` / `gemini-3.8-flash` when your key has capacity |
| `CHAT_FALLBACK_MODELS` | `gemini-3.1-flash-lite` | comma-separated models tried on 503/404 before the first token |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | 768 dims by default |
| `EMBEDDING_DIM` | `768` | must match the pgvector column |
| `EMBEDDING_TOKENS_PER_MINUTE` | `30000` | free-tier embedding quota; raise for paid keys |
| `STORAGE_BACKEND` | `postgres` | `local` for a file-backed index |
| `RERANKER` | `heuristic` | `gemini`, or `none` |
| `VERIFIER_PROVIDER` | `composite` | citation + LLM groundedness |
| `INJECTION_ACTION` | `block` | `sanitize` or `allow` |
| `MAX_CHUNKS` | `1500` | cap per repository |
| `PRICE_*_PER_MTOK` | see `.env.example` | update to current Gemini prices |

Costs are computed from reported token counts; embedding tokens are estimated
(`len(text)/4`) because the embeddings API does not return usage. Prices change:
override the three `PRICE_*` variables.

### Gemini models and free-tier quotas

- `gemini-3.5-flash-lite` is the default because it stayed available during
  testing. `gemini-3.7-flash` and `gemini-3.8-flash` returned `503` under load,
  and `gemini-2.5-*` is closed to new users.
- Free-tier keys allow roughly **15 generate-content requests per minute per
  model**. Each answer uses one chat call plus one verification call, so bursts
  can hit `429`.
- `CHAT_FALLBACK_MODELS` is tried in order on `429`/`503`/timeouts. Each attempt
  is buffered server-side, so a model that dies mid-answer is retried on the next
  model without showing a partial answer; SSE tokens start once an attempt
  succeeds.
- Embeddings have their own free-tier quota: **30k tokens/minute**. The provider
  paces batches with `EMBEDDING_TOKENS_PER_MINUTE` and retries `429` using the
  server's `retryDelay`, so indexing a larger repo takes longer instead of
  failing. Raise the value for a paid key.

## Tests

```bash
cd backend
.venv/bin/python -m pytest -q
```

The suite uses deterministic fake providers and a local index, plus one
integration test that starts a real Postgres via `pgserver` (skipped if the
wheel is unavailable). 49 tests cover chunking, guardrails, RRF fusion, hybrid
retrieval, citation/composite verification, cost math, persistence, the
Postgres adapter, SSE formatting and the HTTP API.

Verified end to end while building this repo:

- 49 tests pass, including the real Postgres + pgvector integration test.
- Real Gemini eval (`--provider gemini`, `gemini-3.5-flash-lite`): recall@5
  **100%**, MRR **0.938**, citation precision **92.3%**, **8/8 answers**,
  **8/8 verified**.
- Real SSE API runs: `sources -> token -> verification -> done`, with token/cost
  metrics recorded for chat and verification.
- The deployed Gradio Space (embedded Postgres, real Gemini) indexed 40 chunks of
  `pallets/click` in 95.7s and answered two questions with citations and 100%
  verification; follow-up questions reused the persisted index.
- The amd64 HF Docker image was driven with `gradio_client`: Postgres data lived
  in `/data/pgdata` and survived a container restart.
- React production build passes (three.js is code-split into its own chunk).

The eval also hit a free-tier `429` and a `503` during testing; the fallback
model completed the request in both cases.

## Security notes

- The API has no authentication. Put it behind an authenticating proxy before
  exposing it; the HF Space is public by default.
- Repository content is untrusted input: prompts wrap it in `<source>` tags and
  instruct the model to ignore instructions inside it, and the input guardrail
  blocks common injection patterns.
- Answers are checked against retrieved sources; unsupported claims are shown
  to the user instead of being silently trusted.
- `GITHUB_TOKEN` is optional and only needed for private repositories. Indexed
  code is sent to the Gemini API for embedding and answering.

## Known limitations

- Job status is in-process memory: single replica only.
- On HF free hardware the disk is ephemeral; the index is rebuilt after a
  restart.
- The HF bundles use `pgserver` (PostgreSQL 16 + pgvector) inside the Python
  process tree. It keeps the demo to a single container, but for production
  point `DATABASE_URL` at a managed Postgres instead.
- `LocalIndex` scans a repo in Python per query and rewrites one JSON file on
  flush; intended for demos and tests, not large corpora.
- The LLM verifier fails open (marked `gemini:error`) if its call fails, so a
  provider outage does not hide correct answers.
- The failover wrapper buffers one model attempt before emitting SSE tokens, so
  time-to-first-token equals that attempt's generation time. This prevents
  half-answers when a provider fails mid-stream.
- No conversation memory: each question is retrieved independently.
- The React UI renders plain text + citation chips, not full Markdown.

## Layout

```
backend/
  reposage/
    api/            FastAPI routes, SSE, schemas
    core/           container, registries, autodiscovery, text helpers
    domain/         models, events, interfaces (ports)
    generation/     prompts, guardrails, verifier, chat service
    ingestion/      loaders, chunker, indexer, jobs
    observability/  cost model, metrics sinks
    providers/      Gemini + fakes
    retrieval/      hybrid retriever, rerankers
    storage/        Postgres/pgvector, local index, embedded Postgres
  tests/            40 tests
  eval/             question set + harness
frontend/           React 19 + Vite + three.js background
gradio_app/         Gradio UI for Spaces
deploy/huggingface/ Dockerfile + Space READMEs
scripts/            Space packaging, ingest CLI
docker-compose.yml  Postgres + backend + frontend (+ optional Gradio)
```
