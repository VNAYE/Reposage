"""Hugging Face Spaces demo (Gradio).

Reuses the exact backend service layer: guardrails, hybrid retrieval,
reranking, verification and cost accounting. Storage is the local
filesystem index because Spaces has no Postgres.

Set ``GEMINI_API_KEY`` as a Space secret before launching.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for _candidate in (_ROOT, _ROOT / "backend", _ROOT.parent / "backend"):
    if (_candidate / "reposage").is_dir():
        sys.path.insert(0, str(_candidate))
        break

import gradio as gr  # noqa: E402

try:  # present on Hugging Face ZeroGPU Spaces, absent locally
    import spaces
except ImportError:  # pragma: no cover - local/dev path
    spaces = None

from reposage.config import Settings  # noqa: E402
from reposage.core.container import Container, build_container  # noqa: E402
from reposage.storage.embedded import EmbeddedPostgres  # noqa: E402
from reposage.domain.events import (  # noqa: E402
    DoneEvent,
    ErrorEvent,
    TokenEvent,
    VerificationEvent,
)
from reposage.domain.models import RepoSpec  # noqa: E402

_container: Container | None = None


def _gpu_ping() -> str:
    """ZeroGPU requires a registered @spaces.GPU handler; this app runs on CPU."""
    return "ok"


if spaces is not None:
    _gpu_ping = spaces.GPU(duration=1)(_gpu_ping)


def configure_database() -> None:
    """Use a managed DATABASE_URL when provided, otherwise start embedded Postgres."""
    if os.getenv("DATABASE_URL"):
        return
    if os.getenv("STORAGE_BACKEND", "postgres").strip().lower() != "postgres":
        return
    if os.getenv("EMBEDDED_POSTGRES", "true").strip().lower() not in {"1", "true", "yes"}:
        return
    os.environ["DATABASE_URL"] = EmbeddedPostgres().start()


def get_container() -> Container:
    global _container
    if _container is None:
        try:
            configure_database()
            _container = build_container(
                Settings(
                    local_index_path=os.getenv("LOCAL_INDEX_PATH", "/data/index.json"),
                    max_chunks=int(os.getenv("MAX_CHUNKS", "800")),
                )
            )
        except Exception as exc:
            raise gr.Error(f"Configuration error: {exc}") from exc
    return _container


async def ensure_ready() -> Container:
    container = get_container()
    await container.startup()
    return container


_SLUG_PART = re.compile(r"^[A-Za-z0-9_.-]+$")
_REF = re.compile(r"^[A-Za-z0-9_./-]+$")


def parse_spec(value: str, ref: str) -> RepoSpec:
    owner, _, name = (value or "").strip().partition("/")
    if not owner or not name or not _SLUG_PART.match(owner) or not _SLUG_PART.match(name):
        raise gr.Error("Use owner/name, for example tiangolo/fastapi.")
    git_ref = (ref or "main").strip() or "main"
    if not _REF.match(git_ref):
        raise gr.Error("Ref may only contain letters, digits, '.', '_', '/' and '-'.")
    return RepoSpec(owner=owner, name=name, ref=git_ref)


async def index_repository(repo: str, ref: str) -> str:
    spec = parse_spec(repo, ref)
    container = await ensure_ready()
    try:
        report = await container.indexing.index_repo(spec)
    except Exception as exc:
        raise gr.Error(str(exc)) from exc
    return (
        f"Indexed **{report.repo}**: {report.chunks:,} chunks from {report.files:,} files "
        f"in {report.duration_ms / 1000:.1f}s."
    )


def _sources_markdown(citations) -> str:
    if not citations:
        return ""
    cited = {citation.source_id: citation for citation in citations}
    lines = ["\n\n---\n**Sources**"]
    for source_id, citation in cited.items():
        lines.append(
            f"- `{citation.path}:{citation.start_line}-{citation.end_line}` "
            f"({source_id}{', ' + citation.symbol if citation.symbol else ''})"
        )
    return "\n".join(lines)


async def chat(message: str, history, repo: str, ref: str):
    history = list(history or [])
    if not (message or "").strip():
        yield history, ""
        return

    spec = parse_spec(repo, ref)
    container = await ensure_ready()

    history.append({"role": "user", "content": message})
    yield history + [{"role": "assistant", "content": "Checking the index…"}], ""

    try:
        report = await container.indexing.ensure_indexed(spec)
    except Exception as exc:
        raise gr.Error(str(exc)) from exc
    if report is not None:
        yield (
            history
            + [
                {
                    "role": "assistant",
                    "content": f"Indexed {report.chunks:,} chunks from {report.files:,} files. Thinking…",
                }
            ],
            "",
        )
    answer = ""
    citations = []
    verification = None
    usage = None

    async for event in container.chat_service.ask(repo=spec.slug, question=message):
        if isinstance(event, TokenEvent):
            answer += event.text
            yield history + [{"role": "assistant", "content": answer}], ""
        elif isinstance(event, VerificationEvent):
            verification = event.result
        elif isinstance(event, DoneEvent):
            citations = event.citations
            usage = event.usage
        elif isinstance(event, ErrorEvent):
            yield history + [{"role": "assistant", "content": f"**{event.code}**: {event.message}"}], ""
            return

    footer = _sources_markdown(citations)
    if verification is not None:
        verdict = "supported by the sources" if verification.supported else "needs review"
        footer += (
            f"\n\n**Verification:** {verdict} ({verification.score:.0%}) · {verification.verifier}"
        )
    if usage is not None:
        footer += (
            f"\n\n<span class='rs-usage'>{usage.total_tokens:,} tokens · "
            f"${usage.cost_usd:.5f} · {usage.latency_ms:.0f} ms</span>"
        )

    yield history + [{"role": "assistant", "content": answer + footer}], ""


CSS = """
.rs-usage { opacity: 0.6; font-size: 12px; }
"""

with gr.Blocks() as demo:
    gr.Markdown(
        "# RepoSage\n"
        "Ask questions about a public GitHub repository. Answers are grounded in retrieved "
        "code and cite the files they used."
    )
    with gr.Row():
        repo_box = gr.Textbox(value="tiangolo/fastapi", label="Repository", scale=4)
        ref_box = gr.Textbox(value="main", label="Ref", scale=1)
        index_button = gr.Button("Index", scale=1)
    index_status = gr.Markdown("")
    chatbot = gr.Chatbot(label="RepoSage", height=520)
    with gr.Row():
        message_box = gr.Textbox(
            placeholder="How does dependency injection work?",
            label="Question",
            scale=4,
        )
        send_button = gr.Button("Send", scale=1)

    index_button.click(index_repository, [repo_box, ref_box], [index_status])
    send_button.click(chat, [message_box, chatbot, repo_box, ref_box], [chatbot, message_box])
    message_box.submit(chat, [message_box, chatbot, repo_box, ref_box], [chatbot, message_box])

    gpu_ping = gr.Button("gpu-ping", visible=False)
    gpu_ping.click(_gpu_ping, None, None)

demo.queue(default_concurrency_limit=1)

if __name__ == "__main__":
    demo.launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", os.getenv("PORT", "7860"))),
        theme=gr.themes.Soft(),
        css=CSS,
    )
