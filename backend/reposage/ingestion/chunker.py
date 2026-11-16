"""Turn source files into retrievable chunks."""

from __future__ import annotations

import ast

from reposage.config import Settings
from reposage.core.plugins import Deps, chunkers
from reposage.domain.interfaces import Chunker
from reposage.domain.models import Chunk, SourceFile


class CodeChunker(Chunker):
    """AST-aware for Python, overlapping line windows for everything else.

    A chunk never crosses a top-level function/class boundary when the file
    parses, so a citation always points at one coherent symbol.
    """

    def __init__(self, max_lines: int = 80, overlap_lines: int = 10, min_header_lines: int = 3) -> None:
        if max_lines < 4:
            raise ValueError("chunk_max_lines must be >= 4")
        if not 0 <= overlap_lines < max_lines:
            raise ValueError("chunk_overlap_lines must be in [0, chunk_max_lines)")
        self._max_lines = max_lines
        self._overlap = overlap_lines
        self._min_header_lines = min_header_lines

    def split(self, repo: str, file: SourceFile) -> list[Chunk]:
        chunks: list[Chunk] = []
        if file.language == "python":
            chunks = self._python_chunks(repo, file)
        return chunks or self._window_chunks(repo, file)

    # --- python ------------------------------------------------------------
    def _python_chunks(self, repo: str, file: SourceFile) -> list[Chunk]:
        try:
            tree = ast.parse(file.content)
        except SyntaxError:
            return []
        lines = file.content.splitlines()
        definitions = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        if not definitions:
            return []

        chunks: list[Chunk] = []
        first_line = min(node.lineno for node in definitions)
        if first_line - 1 >= self._min_header_lines:
            chunks.extend(self._emit(repo, file, lines, 1, first_line - 1, "<module>"))

        for node in definitions:
            start = min([node.lineno] + [decorator.lineno for decorator in node.decorator_list])
            end = getattr(node, "end_lineno", None) or node.lineno
            chunks.extend(self._emit(repo, file, lines, start, end, node.name))
        return chunks

    # --- generic -----------------------------------------------------------
    def _window_chunks(self, repo: str, file: SourceFile) -> list[Chunk]:
        lines = file.content.splitlines()
        if not lines:
            return []
        return self._emit(repo, file, lines, 1, len(lines), "")

    # --- shared ------------------------------------------------------------
    def _emit(
        self,
        repo: str,
        file: SourceFile,
        lines: list[str],
        start: int,
        end: int,
        symbol: str,
    ) -> list[Chunk]:
        if end - start + 1 <= self._max_lines:
            chunk = self._chunk(repo, file, lines, start, end, symbol)
            return [chunk] if chunk else []

        chunks: list[Chunk] = []
        step = self._max_lines - self._overlap
        for window_start in range(start, end + 1, step):
            window_end = min(window_start + self._max_lines - 1, end)
            chunk = self._chunk(repo, file, lines, window_start, window_end, symbol)
            if chunk:
                chunks.append(chunk)
            if window_end >= end:
                break
        return chunks

    @staticmethod
    def _chunk(
        repo: str,
        file: SourceFile,
        lines: list[str],
        start: int,
        end: int,
        symbol: str,
    ) -> Chunk | None:
        content = "\n".join(lines[start - 1 : end]).strip("\n")
        if not content.strip():
            return None
        return Chunk(
            id=Chunk.build_id(repo, file.path, start, end),
            repo=repo,
            path=file.path,
            start_line=start,
            end_line=end,
            language=file.language,
            symbol=symbol,
            content=content,
        )


@chunkers.register("code")
def _build_code_chunker(settings: Settings, deps: Deps | None = None) -> Chunker:
    return CodeChunker(
        max_lines=settings.chunk_max_lines,
        overlap_lines=settings.chunk_overlap_lines,
    )
