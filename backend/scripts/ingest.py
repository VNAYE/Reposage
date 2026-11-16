"""Index a repository from the command line.

    python -m scripts.ingest tiangolo/fastapi --ref master
    python -m scripts.ingest demo --source local --ref eval/fixtures/demo_repo
"""

from __future__ import annotations

import argparse
import asyncio

from reposage.config import Settings
from reposage.core.container import build_container
from reposage.domain.models import RepoSpec


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="owner/name, or any label when --source local")
    parser.add_argument("--ref", default="main")
    parser.add_argument("--source", choices=["github", "local"], default="github")
    args = parser.parse_args()

    owner, _, name = args.slug.partition("/")
    if args.source == "github" and not (owner and name):
        parser.error("github source needs owner/name")
    args.owner = owner or "local"
    args.name = name or "repo"
    return args


async def run(args: argparse.Namespace) -> None:
    container = build_container(Settings())
    await container.startup()
    try:
        spec = RepoSpec(owner=args.owner, name=args.name, ref=args.ref, source=args.source)
        report = await container.indexing.index_repo(spec)
        print(report.to_dict())
    finally:
        await container.shutdown()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
