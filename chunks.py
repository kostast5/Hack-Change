"""Нарезка базы знаний по заголовкам markdown."""

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from config import KB_NAMES, find_file


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_cache: dict[tuple[str, int], list["Chunk"]] = {}


@dataclass(frozen=True)
class Chunk:
    path: str
    heading: str
    text: str


def _meaningful(body: str) -> bool:
    return sum(character.isalnum() for character in body) >= 20


def split_markdown(text: str) -> list[tuple[str, str]]:
    """Возвращает пары (цепочка заголовков, текст раздела)."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    stack: list[tuple[int, str]] = []
    heading = ""
    buf: list[str] = []
    sections: list[tuple[str, str]] = []

    def flush() -> None:
        nonlocal buf
        body = "\n".join(buf).strip()
        buf = []
        title = heading or "Введение"
        if _meaningful(body):
            sections.append((title, body))

    for line in lines:
        match = _HEADING.match(line.strip())
        if not match:
            buf.append(line)
            continue
        flush()
        level = len(match.group(1))
        title = match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        heading = " / ".join(item[1] for item in stack)
    flush()
    return sections


def _read_zip(path: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if name.startswith("__MACOSX/") or name.endswith("/"):
                continue
            if Path(name).suffix.lower() not in {".md", ".txt"}:
                continue
            text = archive.read(name).decode("utf-8-sig", errors="replace")
            if not text.strip():
                continue
            posix = name.replace("\\", "/")
            for heading, body in split_markdown(text):
                chunks.append(Chunk(posix, heading, body))
    if not chunks:
        raise ValueError("База знаний не содержит фрагментов .md или .txt")
    return chunks


def load_chunks(path: Path | None = None) -> list[Chunk]:
    if path is None:
        path = find_file(*KB_NAMES)
    path = Path(path)
    key = (str(path.resolve()), path.stat().st_mtime_ns)
    cached = _cache.get(key)
    if cached is None:
        cached = _read_zip(path)
        _cache.clear()
        _cache[key] = cached
    return cached
