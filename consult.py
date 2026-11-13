"""consult(messages) — общая точка для solution.py и веб-чата.

Текст ответа собирается из prompt.txt через consultant.build_messages.
Поиск остаётся в retrieve.py: фильтр ветки search-rag отсекает файлы
про тарифы, пороги мощности и данные для оценки, поэтому он не подключён.
Заявка остаётся пустой: её включает консультант, когда клиент сам согласен.
"""

import sys

import httpx

from config import ANSWER_LIMIT, FALLBACK, LLM_KEY, LLM_MODEL, MAX_TOKENS, TEMPERATURE
from consultant import build_messages, clean_answer, parse_dialog
from contract import ConsultResult, LeadDraft, Source
from chunks import Chunk, load_chunks
from dialogue import last_user_text, normalize_messages, prior_user_text
from llm import can_call, make_client, post, safe_error
from retrieve import retrieve


def normalize_answer(text: str) -> str:
    flat = clean_answer(text)
    if not flat:
        return FALLBACK
    if len(flat) > ANSWER_LIMIT:
        flat = flat[:ANSWER_LIMIT].rstrip()
    return flat or FALLBACK


def _as_messages(messages) -> list[dict]:
    if isinstance(messages, str):
        parsed = parse_dialog(messages)
        if parsed:
            return parsed
        return [{"role": "user", "content": ""}]
    return normalize_messages(messages)


def _context(sources: list[Source]) -> str:
    blocks = []
    for source in sources:
        blocks.append(f"{source.path} ({source.heading}): {source.quote}")
    return "\n\n".join(blocks)


def write_answer(client: httpx.Client, messages: list[dict], sources: list[Source]) -> str:
    """Текст для судьи и для чата. Правила и форма ответа — в prompt.txt."""
    if not can_call(client, LLM_KEY):
        return FALLBACK
    payload = {
        "model": LLM_MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "messages": build_messages(messages, _context(sources)),
    }
    for attempt in range(2):
        try:
            result = post(client, "/chat/completions", LLM_KEY, payload)
            content = result["choices"][0]["message"].get("content") or ""
            if isinstance(content, list):
                content = " ".join(str(part) for part in content)
            cleaned = clean_answer(content)
            if cleaned:
                return cleaned
            raise ValueError("LLM вернула пустой ответ")
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError, OSError) as exc:
            print(f"LLM попытка {attempt + 1}: {safe_error(exc)}", file=sys.stderr)
    return FALLBACK


def consult(messages, client: httpx.Client | None = None, chunks: list[Chunk] | None = None) -> ConsultResult:
    """Возвращает текст, источники и пустой черновик заявки."""
    prepared = _as_messages(messages)
    question = last_user_text(prepared)
    facts = prior_user_text(prepared)
    if chunks is None:
        chunks = load_chunks()
    own_client = False
    if client is None:
        client = make_client()
        own_client = True
    try:
        sources = retrieve(question, chunks, client=client, facts=facts) if question else []
        if not question or not can_call(client, LLM_KEY):
            text = FALLBACK
        else:
            text = write_answer(client, prepared, sources)
        return ConsultResult(text=normalize_answer(text), sources=sources, lead=LeadDraft())
    finally:
        if own_client:
            client.close()
