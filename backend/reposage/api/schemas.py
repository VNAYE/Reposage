"""Request/response models for the HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

_SLUG = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
_PART = r"^[A-Za-z0-9_.-]+$"


class RepoRequest(BaseModel):
    owner: str = Field(pattern=_PART, max_length=100)
    name: str = Field(pattern=_PART, max_length=100)
    ref: str = Field(default="main", min_length=1, max_length=200)


class ChatRequest(BaseModel):
    repo: str = Field(pattern=_SLUG, max_length=200)
    question: str = Field(min_length=1, max_length=4000)


class RepoResponse(BaseModel):
    slug: str
    chunks: int


class JobResponse(BaseModel):
    job_id: str
    repo: str
    status: str
    error: str = ""
    report: dict[str, Any] | None = None


class DeleteResponse(BaseModel):
    deleted: str
