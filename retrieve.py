"""Выбор фрагментов базы. Роль «Поиск» заменяет rank_chunks."""

import math
import re
import sys
import threading
from collections import Counter

import httpx

from chunks import Chunk
from config import EMB_KEY, RERANK_KEY, RERANKER_TOP_N, TOP_K
from contract import Source
from llm import can_call, embeddings, rerank, safe_error

_index_lock = threading.Lock()

# Поверхностные формы. Отрезаются до стемминга.
_STOP = {
    "это", "этот", "эта", "эти", "этой", "этом", "этого", "этому", "этих", "этим", "эту",
    "как", "что", "чтобы", "для", "или", "при", "уже", "еще", "если", "так", "там", "тут",
    "вот", "надо", "нужно", "можно", "будет", "будут", "быть", "было", "были", "есть",
    "нет", "да", "мы", "вы", "они", "его", "ее", "их", "вам", "нас", "вас", "мне",
    "мой", "моя", "мои", "наш", "наша", "наши", "ваш", "ваша", "ваши",
    "кто", "где", "когда", "тоже", "также", "только", "просто", "очень", "сейчас",
    "потом", "тогда", "почему", "зачем", "пока", "вообще", "через", "после", "перед",
    "между", "около", "примерно", "всего", "потому", "поэтому", "который", "которая",
    "которые", "которое", "каких", "какой", "какая", "какие", "какое", "каком", "какую",
    "такой", "такая", "такие", "такое", "таких", "другой", "другая", "другие", "других",
    "свой", "своя", "свои", "своих", "весь", "вся", "все", "всех", "всем",
    "хочу", "хотим", "может", "могут", "можете", "стоит", "стоят",
    "подскажите", "скажите", "объясните",
}

_ENDINGS = (
    "иями", "ами", "ями", "ными", "ого", "ему", "ому", "ыми", "ими",
    "ться", "тся", "ная", "ное", "ные", "ный", "ных", "ным", "ную", "ной",
    "иями", "иях", "иям", "ией", "ии", "ия",
    "ая", "яя", "ое", "ее", "ые", "ие", "ой", "ый", "ий", "ую", "юю",
    "ов", "ев", "ам", "ям", "ах", "ях", "ом", "ем", "ей", "ою", "ею",
    "а", "я", "ы", "и", "е", "у", "ю", "о", "ь",
)
_TOKEN = re.compile(r"\d+|[a-zа-я]{3,}")

_index_id: int | None = None
_index_tokens: list[list[str]] | None = None


def _stem(token: str) -> str:
    if token.isdigit() or len(token) <= 4:
        return token
    for ending in _ENDINGS:
        if token.endswith(ending) and len(token) - len(ending) >= 3:
            return token[: -len(ending)]
    return token


def tokenize(text: str) -> list[str]:
    lowered = text.lower().replace("ё", "е")
    for dash in ("—", "–", "−", "-", "·", "/"):
        lowered = lowered.replace(dash, " ")
    tokens = []
    for token in _TOKEN.findall(lowered):
        if token in _STOP:
            continue
        if token.isdigit():
            if len(token) >= 2:
                tokens.append(token)
            continue
        stem = _stem(token)
        if len(stem) >= 3 and stem not in _STOP:
            tokens.append(stem)
    return tokens


def _bm25(query: list[str], docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> list[float]:
    if not docs:
        return []
    terms = list(dict.fromkeys(query))
    if not terms:
        return [0.0] * len(docs)
    count = len(docs)
    df: Counter[str] = Counter()
    lengths = [len(doc) or 1 for doc in docs]
    average = sum(lengths) / count
    for doc in docs:
        df.update(set(doc))
    scores = []
    for doc, length in zip(docs, lengths):
        freq = Counter(doc)
        score = 0.0
        for term in terms:
            seen = freq.get(term, 0)
            if not seen:
                continue
            idf = math.log(1.0 + (count - df[term] + 0.5) / (df[term] + 0.5))
            denom = seen + k1 * (1.0 - b + b * length / average)
            score += idf * (seen * (k1 + 1.0) / denom)
        scores.append(score)
    return scores


def _docs(chunks: list[Chunk]) -> list[list[str]]:
    global _index_id, _index_tokens
    with _index_lock:
        if _index_id != id(chunks) or _index_tokens is None:
            _index_tokens = [tokenize(chunk.text) + tokenize(chunk.heading) for chunk in chunks]
            _index_id = id(chunks)
        return _index_tokens


def rank_chunks(question: str, facts: str, chunks: list[Chunk]) -> list[tuple[float, Chunk]]:
    """Полный текст раздела, не начало файла.

    Роль «Поиск» заменяет эту функцию. Результат — пары (оценка, чанк)
    по убыванию оценки, не длиннее TOP_K. Нулевые оценки не возвращаются.
    """
    if not chunks or not question.strip():
        return []
    docs = _docs(chunks)
    question_scores = _bm25(tokenize(question), docs)
    fact_tokens = tokenize(facts)
    if fact_tokens:
        fact_scores = _bm25(fact_tokens, docs)
    else:
        fact_scores = [0.0] * len(chunks)
    ranked = [
        (question_scores[i] + 0.5 * fact_scores[i], chunks[i])
        for i in range(len(chunks))
        if question_scores[i] + 0.5 * fact_scores[i] > 0
    ]
    ranked.sort(key=lambda item: (-item[0], item[1].path, item[1].heading))
    return ranked[:TOP_K]


def make_quote(chunk: Chunk, query: str, limit: int = 1800) -> str:
    paragraphs = []
    for part in re.split(r"\n\s*\n", chunk.text.strip()):
        flat = " ".join(part.split())
        if flat and re.search(r"[0-9A-Za-zА-Яа-яЁё]", flat):
            paragraphs.append(flat)
    if not paragraphs:
        return ""
    whole = "\n".join(paragraphs)
    if len(whole) <= limit:
        return whole
    query_tokens = set(tokenize(query))
    best = max(
        range(len(paragraphs)),
        key=lambda index: (len(query_tokens & set(tokenize(paragraphs[index]))), -index),
    )
    picked = [best]
    while True:
        added = False
        for nxt in (min(picked) - 1, max(picked) + 1):
            if nxt < 0 or nxt >= len(paragraphs) or nxt in picked:
                continue
            trial = sorted(picked + [nxt])
            text = "\n".join(paragraphs[index] for index in trial)
            if len(text) <= limit:
                picked.append(nxt)
                added = True
                break
        if not added:
            break
    text = "\n".join(paragraphs[index] for index in sorted(picked))
    if len(text) > limit:
        text = text[:limit].rstrip()
    return text


def _apply_embeddings(client, question: str, ranked: list[tuple[float, Chunk]]) -> list[tuple[float, Chunk]]:
    if not can_call(client, EMB_KEY) or len(ranked) < 2:
        return ranked
    try:
        texts = [question] + [chunk.heading + "\n" + make_quote(chunk, question, 500) for _, chunk in ranked]
        vectors = embeddings(client, texts)
        scores = [sum(left * right for left, right in zip(vectors[0], vector)) for vector in vectors[1:]]
        order = sorted(range(len(ranked)), key=lambda index: scores[index], reverse=True)
        return [(scores[index], ranked[index][1]) for index in order]
    except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError) as exc:
        print(f"Embeddings: {safe_error(exc)}; продолжаем без них", file=sys.stderr)
        return ranked


def _apply_rerank(client, question: str, ranked: list[tuple[float, Chunk]]) -> list[tuple[float, Chunk]]:
    if not can_call(client, RERANK_KEY) or not ranked:
        return ranked
    try:
        documents = [
            f"{chunk.path}\n{chunk.heading}\n{make_quote(chunk, question, 800)}"
            for _, chunk in ranked
        ]
        indices = rerank(client, question, documents, min(RERANKER_TOP_N, len(documents)))
        picked = []
        seen: set[int] = set()
        for index in indices:
            if 0 <= index < len(ranked) and index not in seen:
                picked.append(ranked[index])
                seen.add(index)
        if not picked:
            return ranked
        rest = [item for index, item in enumerate(ranked) if index not in seen]
        return picked + rest
    except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError) as exc:
        print(f"Reranker: {safe_error(exc)}; продолжаем без него", file=sys.stderr)
        return ranked


def retrieve(question: str, chunks: list[Chunk], client=None, facts: str = "") -> list[Source]:
    """Фрагменты для ответа: путь, заголовок, цитата, оценка."""
    ranked = rank_chunks(question, facts, chunks)
    ranked = _apply_embeddings(client, question, ranked)
    ranked = _apply_rerank(client, question, ranked)
    sources = []
    for score, chunk in ranked:
        quote = make_quote(chunk, question)
        if not quote:
            continue
        sources.append(Source(path=chunk.path, heading=chunk.heading, quote=quote, score=float(score)))
    return sources
