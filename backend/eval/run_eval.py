"""Evaluation harness: retrieval accuracy and answer quality for a question set.

    python -m eval.run_eval                     # offline, fake providers
    python -m eval.run_eval --provider gemini   # real Gemini, needs GEMINI_API_KEY
    python -m eval.run_eval --retrieval-only

Exit code is 1 when recall@k falls below ``--min-recall``, so CI can gate on it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from reposage.config import Settings
from reposage.core.container import build_container
from reposage.domain.events import DoneEvent, ErrorEvent, TokenEvent, VerificationEvent
from reposage.domain.models import RepoSpec


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default=str(Path(__file__).with_name("questions.json")))
    parser.add_argument("--provider", choices=["fake", "gemini"], default=None)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--min-recall", type=float, default=0.6)
    parser.add_argument("--retrieval-only", action="store_true")
    return parser.parse_args()


async def evaluate(args: argparse.Namespace) -> bool:
    questions_path = Path(args.questions).resolve()
    payload = json.loads(questions_path.read_text(encoding="utf-8"))
    repo_path = (questions_path.parent / payload["path"]).resolve()
    provider = args.provider or ("gemini" if os.getenv("GEMINI_API_KEY") else "fake")

    workdir = tempfile.mkdtemp(prefix="reposage-eval-")
    settings = Settings(
        chat_provider=provider,
        embedding_provider=provider,
        storage_backend="local",
        metrics_backend="local",
        local_index_path=str(Path(workdir) / "index.json"),
        verify_answers=not args.retrieval_only,
        verifier_provider="composite",
    )
    container = build_container(settings)
    await container.startup()

    try:
        spec = RepoSpec(owner="eval", name=payload["name"], ref=str(repo_path), source="local")
        report = await container.indexing.index_repo(spec)
        print(f"indexed {report.chunks} chunks from {report.files} files ({provider} embeddings)\n")

        hits = 0
        reciprocal_ranks = 0.0
        citation_hits = 0
        citation_total = 0
        verified_count = 0
        answered = 0

        for item in payload["questions"]:
            question = item["question"]
            started = time.perf_counter()
            sources = await container.retriever.retrieve(repo=spec.slug, query=question, limit=args.k)
            retrieval_ms = (time.perf_counter() - started) * 1000
            paths = [source.chunk.path for source in sources]
            rank = next(
                (position for position, path in enumerate(paths, start=1) if path in item["expected_paths"]),
                None,
            )
            hits += 1 if rank else 0
            reciprocal_ranks += 1.0 / rank if rank else 0.0

            line = (
                f"{item['id']:<4} {'HIT ' if rank else 'MISS'} "
                f"rank={rank or '-':<4} {retrieval_ms:6.0f}ms  {question}"
            )
            if not args.retrieval_only:
                answer, citations, verification = await collect_answer(container, spec, question)
                answered += 1 if answer else 0
                for citation in citations:
                    citation_total += 1
                    citation_hits += 1 if citation.path in item["expected_paths"] else 0
                if verification is not None:
                    verified_count += 1 if verification.supported else 0
                line += f"  citations={len(citations)} verified={verification.supported if verification else '-'}"
            print(line)

        count = len(payload["questions"])
        recall = hits / count if count else 0.0
        print("\nsummary")
        print(f"  recall@{args.k}        {recall:.2%} ({hits}/{count})")
        print(f"  MRR                {reciprocal_ranks / count:.3f}")
        if not args.retrieval_only:
            precision = citation_hits / citation_total if citation_total else 0.0
            print(f"  citation precision {precision:.2%} ({citation_hits}/{citation_total})")
            print(f"  answers produced   {answered}/{count}")
            print(f"  verified answers   {verified_count}/{count}")
        return recall >= args.min_recall
    finally:
        await container.shutdown()


async def collect_answer(container, spec: RepoSpec, question: str):
    text: list[str] = []
    citations = []
    verification = None
    async for event in container.chat_service.ask(repo=spec.slug, question=question):
        if isinstance(event, TokenEvent):
            text.append(event.text)
        elif isinstance(event, VerificationEvent):
            verification = event.result
        elif isinstance(event, DoneEvent):
            citations = event.citations
        elif isinstance(event, ErrorEvent):
            print(f"    answer error: {event.code} {event.message}")
            return "", [], verification
    return "".join(text), citations, verification


def main() -> None:
    args = parse_args()
    passed = asyncio.run(evaluate(args))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
