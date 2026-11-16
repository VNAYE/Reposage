"""Background indexing jobs.

ponytail: in-process dict, so job status is lost on restart and not shared
across replicas. Swap for Redis/Postgres if the API is ever scaled out.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from reposage.domain.interfaces import IndexingService
from reposage.domain.models import IndexReport, RepoSpec


@dataclass
class IndexJob:
    id: str
    repo: str
    status: str = "queued"
    report: IndexReport | None = None
    error: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "repo": self.repo,
            "status": self.status,
            "error": self.error,
            "report": self.report.to_dict() if self.report else None,
        }


class IndexJobStore:
    def __init__(self, indexing: IndexingService, max_jobs: int = 50) -> None:
        self._indexing = indexing
        self._max_jobs = max_jobs
        self._jobs: dict[str, IndexJob] = {}

    def create(self, spec: RepoSpec) -> IndexJob:
        job = IndexJob(id=uuid.uuid4().hex[:12], repo=spec.slug)
        self._jobs[job.id] = job
        self._prune()
        return job

    async def run(self, job: IndexJob, spec: RepoSpec) -> None:
        job.status = "running"
        try:
            job.report = await self._indexing.index_repo(spec)
            job.status = "succeeded"
        except Exception as exc:  # surfaced to the client through the job
            job.status = "failed"
            job.error = str(exc)

    def get(self, job_id: str) -> IndexJob | None:
        return self._jobs.get(job_id)

    def _prune(self) -> None:
        if len(self._jobs) <= self._max_jobs:
            return
        for job_id in sorted(self._jobs, key=lambda key: self._jobs[key].created_at)[
            : len(self._jobs) - self._max_jobs
        ]:
            del self._jobs[job_id]
