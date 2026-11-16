from __future__ import annotations

from reposage.domain.models import SourceFile
from reposage.ingestion.chunker import CodeChunker

SOURCE = '''"""Module docstring."""
import os

CONSTANT = 1

def alpha(x):
    """Doc."""
    return x + 1


class Beta:
    def method(self):
        return 2
'''


def test_python_chunks_follow_symbols() -> None:
    chunker = CodeChunker(max_lines=40, overlap_lines=4)
    chunks = chunker.split("owner/repo", SourceFile(path="mod.py", content=SOURCE, language="python"))

    symbols = {chunk.symbol for chunk in chunks}
    assert {"<module>", "alpha", "Beta"} <= symbols

    alpha = next(chunk for chunk in chunks if chunk.symbol == "alpha")
    lines = SOURCE.splitlines()
    assert alpha.content == "\n".join(lines[alpha.start_line - 1 : alpha.end_line])
    assert alpha.start_line == 6


def test_long_function_is_windowed_with_overlap() -> None:
    body = "\n".join(f"    value_{index} = {index}" for index in range(40))
    source = f"def huge():\n{body}\n"
    chunker = CodeChunker(max_lines=10, overlap_lines=2)
    chunks = chunker.split("owner/repo", SourceFile(path="huge.py", content=source, language="python"))

    assert len(chunks) > 1
    assert all(chunk.symbol == "huge" for chunk in chunks)
    assert chunks[0].start_line == 1
    assert chunks[-1].end_line == 41
    assert chunks[1].start_line == chunks[0].start_line + 8


def test_non_python_files_use_line_windows() -> None:
    source = "\n".join(f"const value{index} = {index};" for index in range(1, 26))
    chunker = CodeChunker(max_lines=10, overlap_lines=2)
    chunks = chunker.split("owner/repo", SourceFile(path="app.js", content=source, language="javascript"))

    assert len(chunks) >= 3
    assert chunks[0].start_line == 1
    assert chunks[-1].end_line == 25
    assert all(chunk.language == "javascript" for chunk in chunks)


def test_empty_file_produces_no_chunks() -> None:
    chunker = CodeChunker()
    assert chunker.split("owner/repo", SourceFile(path="blank.py", content="   \n\n", language="python")) == []
