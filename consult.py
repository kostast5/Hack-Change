"""consult(messages) — общая точка для solution.py и веб-чата.

Текст ответа собирается из prompt.txt через consultant.build_messages.
Поиск остаётся в retrieve.py: фильтр ветки search-rag отсекает файлы
про тарифы, пороги мощности и данные для оценки, поэтому он не подключён.
Заявка заполняется только когда клиент сам согласен на контакт.
Слабый поиск не идёт в модель: бот задаёт уточняющий вопрос.
Повтор того же диалога берётся из кэша и в модель не отправляется.
"""

import sys

import httpx

from config import (
    ANSWER_LIMIT,
    ANSWER_WORD_LIMIT,
    FALLBACK,
    LLM_KEY,
    LLM_MODEL,
    LLM_REASONING_EFFORT,
    MAX_TOKENS,
    TEMPERATURE,
)
from consultant import build_messages, clean_answer, clean_answer_lines, parse_dialog
from contract import ConsultResult, LeadDraft, Source
from chunks import Chunk, load_chunks
from dialogue import last_user_text, normalize_messages, prior_user_text
from flow import (
    CLARIFY,
    TASK_BUTTONS,
    build_lead,
    buttons_for,
    cache_get,
    cache_key,
    cache_put,
    client_is_ready,
    dialog_memory,
    lead_from_cache,
    retrieval_is_weak,
    sources_from_cache,
    strip_ui_greeting,
)
from llm import can_call, make_client, post, safe_error
from retrieve import retrieve


def _clip_words(text: str, limit: int) -> str:
    if limit <= 0:
        return text
    parts = text.split()
    if len(parts) <= limit:
        return text
    clipped = " ".join(parts[:limit]).rstrip(".,;:")
    return clipped + "…"


def _dedupe_suggestions(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        label = (item or "").strip()
        key = label.lower().replace("ё", "е")
        if not label or key in seen:
            continue
        seen.add(key)
        out.append(label)
    return out


def _is_escalation(text: str) -> bool:
    flat = (text or "").strip()
    return flat == FALLBACK or flat.startswith("По этому вопросу лучше продолжить")


def normalize_answer(text: str, *, preserve_lines: bool = False) -> str:
    if _is_escalation(text):
        return FALLBACK
    if preserve_lines:
        flat = clean_answer_lines(text)
    else:
        flat = clean_answer(text)
    if not flat:
        return FALLBACK
    clipped = _clip_words(flat.replace("\n", " "), ANSWER_WORD_LIMIT)
    if preserve_lines:
        words = clipped.split()
        if len(words) > 12:
            mid = len(words) // 2
            flat = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])
        else:
            flat = clipped
    else:
        flat = clipped
    if len(flat) > ANSWER_LIMIT:
        flat = flat[:ANSWER_LIMIT].rstrip()
    return flat or FALLBACK


def _llm_message_text(message: dict) -> str:
    content = message.get("content") or ""
    if isinstance(content, list):
        content = " ".join(str(part) for part in content)
    text = str(content).strip()
    if text:
        return text
    # Gemini Hydrogen при reasoning иногда оставляет content пустым, а рассуждения — в reasoning.
    alt = message.get("text")
    if isinstance(alt, str) and alt.strip():
        return alt.strip()
    return ""


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
    base = {
        "model": LLM_MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "messages": build_messages(messages, _context(sources), client_memory=dialog_memory(messages)),
    }
    effort = (LLM_REASONING_EFFORT or "").strip().lower()
    payloads: list[dict] = []
    if effort in {"low", "medium", "high"}:
        payloads.append({**base, "reasoning": {"effort": effort}})
    payloads.append(dict(base))
    last_error: BaseException | None = None
    for index, payload in enumerate(payloads):
        for attempt in range(2):
            try:
                result = post(client, "/chat/completions", LLM_KEY, payload)
                message = result["choices"][0]["message"]
                cleaned = clean_answer(_llm_message_text(message))
                if cleaned:
                    return cleaned
                last_error = ValueError("LLM вернула пустой ответ")
            except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError, OSError) as exc:
                last_error = exc
                print(
                    f"LLM попытка {index + 1}.{attempt + 1}: {safe_error(exc)}",
                    file=sys.stderr,
                )
    if last_error is not None:
        print(f"LLM ответ не получен: {safe_error(last_error)}", file=sys.stderr)
    return FALLBACK


def _lead_for(messages: list[dict], sources: list[Source]) -> LeadDraft:
    if not client_is_ready(last_user_text(messages)):
        return LeadDraft()
    return build_lead(messages, sources)


def _remember(key: str, text: str, sources: list[Source], suggestions: list[str], lead: LeadDraft) -> None:
    if _is_escalation(text):
        return
    cache_put(
        key,
        {
            "text": text,
            "sources": [
                {"path": source.path, "heading": source.heading, "quote": source.quote, "score": source.score}
                for source in sources
            ],
            "suggestions": suggestions,
            "lead": {
                "ready": lead.ready,
                "full_name": lead.full_name,
                "phone": lead.phone,
                "company": lead.company,
                "summary": lead.summary,
            },
        },
    )


def consult(
    messages,
    client: httpx.Client | None = None,
    chunks: list[Chunk] | None = None,
    *,
    chat_format: bool = False,
) -> ConsultResult:
    """Текст, источники, кнопки и заявка, если клиент сам готов к контакту."""
    prepared = strip_ui_greeting(_as_messages(messages))
    question = last_user_text(prepared)
    facts = prior_user_text(prepared)
    if chunks is None:
        chunks = load_chunks()
    own_client = False
    if client is None:
        client = make_client()
        own_client = True
    try:
        key = cache_key(prepared)
        cached = cache_get(key) if question else None
        if cached and cached.get("text") and not _is_escalation(str(cached.get("text"))):
            return ConsultResult(
                text=normalize_answer(str(cached.get("text")), preserve_lines=chat_format),
                sources=sources_from_cache(cached.get("sources")),
                lead=lead_from_cache(cached.get("lead")),
                suggestions=_dedupe_suggestions(
                    [str(item) for item in cached.get("suggestions") or [] if str(item).strip()]
                ),
                cached=True,
            )
        sources = retrieve(question, chunks, client=client, facts=facts) if question else []
        ready = client_is_ready(question)
        weak = bool(question) and retrieval_is_weak(question, facts, chunks) and not ready
        suggestions: list[str] = []
        if not question or not can_call(client, LLM_KEY):
            text = FALLBACK
        elif weak:
            text = CLARIFY
            suggestions = list(TASK_BUTTONS)
        else:
            text = write_answer(client, prepared, sources)
        text = normalize_answer(text, preserve_lines=chat_format)
        if not suggestions:
            suggestions = buttons_for(text, prepared)
        suggestions = _dedupe_suggestions(suggestions)
        lead = _lead_for(prepared, sources)
        _remember(key, text, sources, suggestions, lead)
        return ConsultResult(text=text, sources=sources, lead=lead, suggestions=suggestions)
    finally:
        if own_client:
            client.close()
