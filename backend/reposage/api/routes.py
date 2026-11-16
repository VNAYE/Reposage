"""HTTP routes. All state comes from the injected container."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Query

from reposage.api.schemas import ChatRequest, DeleteResponse, JobResponse, RepoRequest, RepoResponse
from reposage.api.sse import sse_response
from reposage.core.container import Container
from reposage.domain.models import RepoSpec

log = logging.getLogger(__name__)

_OWNER = Path(pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
_NAME = Path(pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)


def build_router(container: Container) -> APIRouter:
    router = APIRouter(prefix="/api")
    settings = container.settings

    @router.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "app": settings.app_name,
            "chat_provider": container.chat.name,
            "chat_model": container.chat.model,
            "embedding_model": container.embeddings.model,
            "storage": settings.storage_backend,
            "reranker": settings.reranker,
            "verify_answers": settings.verify_answers,
        }

    @router.get("/repos", response_model=list[RepoResponse])
    async def list_repos() -> list[RepoResponse]:
        repos = await container.index.list_repos()
        return [RepoResponse(**repo.to_dict()) for repo in repos]

    @router.post("/repos", response_model=JobResponse, status_code=202)
    async def index_repo(request: RepoRequest, background: BackgroundTasks) -> JobResponse:
        spec = RepoSpec(owner=request.owner, name=request.name, ref=request.ref)
        job = container.jobs.create(spec)
        background.add_task(container.jobs.run, job, spec)
        return JobResponse(**job.to_dict())

    @router.get("/repos/jobs/{job_id}", response_model=JobResponse)
    async def job_status(job_id: str) -> JobResponse:
        job = container.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return JobResponse(**job.to_dict())

    @router.delete("/repos/{owner}/{name}", response_model=DeleteResponse)
    async def delete_repo(owner: str = _OWNER, name: str = _NAME) -> DeleteResponse:
        slug = f"{owner}/{name}"
        await container.index.delete_repo(slug)
        await container.index.flush()
        return DeleteResponse(deleted=slug)

    @router.post("/chat")
    async def chat(request: ChatRequest):
        return sse_response(
            container.chat_service.ask(repo=request.repo, question=request.question)
        )

    @router.get("/metrics")
    async def metrics(hours: int = Query(default=24, ge=1, le=168)) -> dict[str, object]:
        summary = await container.metrics.summary(hours=hours)
        return summary.to_dict()

    return router
