"""разбиение markdown-документов по заголовкам"""
import re
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def split_markdown(text: str, path: str) -> list[dict]:
    chunks = []
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        if text.strip():
            chunks.append({"path": path, "heading": "", "level": 0, "text": text.strip()})
        return chunks

    # текст до первого заголовка
    first_start = matches[0].start()
    preamble = text[:first_start].strip()
    if preamble:
        chunks.append({"path": path, "heading": "", "level": 0, "text": preamble})

    for i, m in enumerate(matches):
        level = len(m.group(1))
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        # включаем сам заголовок в текст чанка для поиска
        full = (heading + "\n" + body).strip() if body else heading
        chunks.append({"path": path, "heading": heading, "level": level, "text": full})

    return chunks


def load_chunks_from_dir(root: str) -> list[dict]:
    root_path = Path(root)
    chunks = []
    for p in sorted(root_path.rglob("*")):
        if p.suffix.lower() not in (".md", ".txt"):
            continue
        if p.name.startswith("."):
            continue
        rel = p.relative_to(root_path).as_posix()
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        if text.strip():
            chunks.extend(split_markdown(text, rel))
    return chunks


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    ch = load_chunks_from_dir(root)
    print(f"Файлов/чанков: {len(ch)}")
    for c in ch[:5]:
        print("---", c["path"], "|", c["heading"])
        print(c["text"][:200])
