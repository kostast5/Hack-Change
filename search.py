"""Поиск по базе знаний: BM25 по чанкам + роутер + (опц.) эмбеддинги."""
import re
from rank_bm25 import BM25Okapi

from sources import Source

TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]{3,}")


def tokenize(text: str) -> list[str]:
    return [t.lower().replace("ё", "е") for t in TOKEN_RE.findall(text)]


class BM25Index:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        corpus = [tokenize(c["text"]) for c in chunks]
        self.bm25 = BM25Okapi(corpus)

    def search(self, query: str, top_k: int = 10) -> list[tuple[dict, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        result = []
        for i in order[:top_k]:
            if scores[i] <= 0:
                continue
            result.append((self.chunks[i], float(scores[i])))
        return result


def to_sources(results, quote_len: int = 240) -> list[Source]:
    out = []
    for chunk, score in results:
        text = chunk["text"]
        quote = text[:quote_len].replace("\n", " ")
        out.append(Source(
            path=chunk["path"],
            heading=chunk["heading"],
            text=text,
            score=score,
            quote=quote,
        ))
    return out


def search(question: str, chunks: list[dict], history: str = "", top_k: int = 8) -> list[Source]:
    """Поиск релевантных чанков с учётом роутера и истории."""
    from router import route
    allowed = set(route(question, history))
    filtered = [c for c in chunks if c["path"] in allowed]
    if not filtered:
        filtered = chunks
    idx = BM25Index(filtered)
    query = question
    if history:
        tail = history.strip().splitlines()[-3:]
        query = question + " " + " ".join(tail)
    results = idx.search(query, top_k=top_k)
    return to_sources(results)


if __name__ == "__main__":
    import sys
    from chunking import load_chunks_from_dir
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    chunks = load_chunks_from_dir(root)
    q = sys.argv[2] if len(sys.argv) > 2 else "солнечная станция"
    res = search(q, chunks, top_k=5)
    for s in res:
        print(f"{s.score:.3f} | {s.path} | {s.heading}")
        print("   ", s.text[:120].replace("\n", " "))