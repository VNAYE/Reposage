"""Fetch source files from GitHub (tarball) or a local directory."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path, PurePosixPath

import httpx

from reposage.config import Settings
from reposage.core.plugins import Deps, repo_loaders
from reposage.domain.interfaces import RepoLoader
from reposage.domain.models import RepoSpec, SourceFile

LANGUAGE_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "shell",
    ".sql": "sql",
    ".md": "markdown",
    ".rst": "rst",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}

SKIP_DIRS = frozenset(
    {
        ".git",
        ".github",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        "vendor",
        "site-packages",
        ".next",
        "coverage",
        "migrations",
    }
)
SKIP_SUFFIXES = (
    ".min.js",
    ".min.css",
    ".map",
    ".lock",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".whl",
)


def _relative_path(name: str) -> str:
    """Strip the ``repo-ref/`` prefix of a GitHub tarball and reject traversal."""
    parts = PurePosixPath(name).parts
    if len(parts) < 2:
        return ""
    relative = PurePosixPath(*parts[1:])
    if relative.is_absolute() or ".." in relative.parts:
        return ""
    return relative.as_posix()


def _is_indexable(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if any(part in SKIP_DIRS for part in parts):
        return False
    if any(part.startswith(".") for part in parts):
        return False
    lower = path.lower()
    if lower.endswith(SKIP_SUFFIXES):
        return False
    return PurePosixPath(path).suffix.lower() in LANGUAGE_BY_EXT


def _make_source(path: str, data: bytes, max_bytes: int) -> SourceFile | None:
    if not data or len(data) > max_bytes or b"\x00" in data[:4096]:
        return None
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not content.strip():
        return None
    language = LANGUAGE_BY_EXT.get(PurePosixPath(path).suffix.lower(), "text")
    return SourceFile(path=path, content=content, language=language)


class GitHubLoader(RepoLoader):
    """Downloads the repository tarball - one request, no clone, no auth required for public repos."""

    name = "github"

    def __init__(self, token: str = "", max_file_bytes: int = 200_000, max_files: int = 800) -> None:
        self._token = token
        self._max_file_bytes = max_file_bytes
        self._max_files = max_files

    async def load(self, spec: RepoSpec) -> list[SourceFile]:
        url = f"https://codeload.github.com/{spec.owner}/{spec.name}/tar.gz/{spec.ref}"
        headers = {"User-Agent": "reposage", "Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            response = await client.get(url, headers=headers)
        if response.status_code == 404:
            raise ValueError(f"repository or ref not found: {spec.slug}@{spec.ref}")
        response.raise_for_status()
        return self._extract(response.content)

    def _extract(self, archive_bytes: bytes) -> list[SourceFile]:
        sources: list[SourceFile] = []
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            for member in archive.getmembers():
                if len(sources) >= self._max_files:
                    break
                if not member.isfile():
                    continue
                path = _relative_path(member.name)
                if not path or not _is_indexable(path):
                    continue
                handle = archive.extractfile(member)
                if handle is None:
                    continue
                source = _make_source(path, handle.read(self._max_file_bytes + 1), self._max_file_bytes)
                if source is not None:
                    sources.append(source)
        if not sources:
            raise ValueError("no indexable source files found (check the ref and repository contents)")
        return sources


class LocalDirectoryLoader(RepoLoader):
    """Indexes a directory on disk. ``spec.ref`` is the path."""

    name = "local"

    def __init__(self, max_file_bytes: int = 200_000, max_files: int = 800) -> None:
        self._max_file_bytes = max_file_bytes
        self._max_files = max_files

    async def load(self, spec: RepoSpec) -> list[SourceFile]:
        root = Path(spec.ref).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"local repository path does not exist: {root}")
        sources: list[SourceFile] = []
        for path in sorted(root.rglob("*")):
            if len(sources) >= self._max_files:
                break
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if not _is_indexable(relative):
                continue
            source = _make_source(
                relative,
                path.read_bytes()[: self._max_file_bytes + 1],
                self._max_file_bytes,
            )
            if source is not None:
                sources.append(source)
        if not sources:
            raise ValueError(f"no indexable source files found under {root}")
        return sources


@repo_loaders.register("github")
def _build_github(settings: Settings, deps: Deps | None = None) -> RepoLoader:
    return GitHubLoader(
        token=settings.github_token,
        max_file_bytes=settings.max_file_bytes,
        max_files=settings.max_files,
    )


@repo_loaders.register("local")
def _build_local(settings: Settings, deps: Deps | None = None) -> RepoLoader:
    return LocalDirectoryLoader(
        max_file_bytes=settings.max_file_bytes,
        max_files=settings.max_files,
    )
