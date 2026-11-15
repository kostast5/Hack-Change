"""consult(messages) — общая точка для solution.py и веб-чата.

Текст ответа собирается из prompt.txt через consultant.build_messages.
Поиск остаётся в retrieve.py: фильтр ветки search-rag отсекает файлы
про тарифы, пороги мощности и данные для оценки, поэтому он не подключён.
Заявка заполняется только когда клиент сам согласен на контакт.
Слабый поиск не идёт в модель: бот задаёт уточняющий вопрос.
Повтор того же диалога берётся из кэша и в модель не отправляется.
"""

import re
import sys

import httpx

from config import (
    ANSWER_LIMIT,
    ANSWER_WORD_LIMIT,
    CHAT_MAX_TOKENS,
    FALLBACK,
    LLM_KEY,
    LLM_MODEL,
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
from llm import can_call, completion_extras, make_client, post, safe_error
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


def _user_rejects_escalation(messages: list[dict]) -> bool:
    """Клиент не хочет заявку — отвечаем по делу, не повторяем FALLBACK."""
    user = last_user_text(messages).lower().replace("ё", "е").strip()
    if not user or len(user) > 32:
        return False
    if not re.fullmatch(r"(чего|что|зачем|почему|нет|неа|не хочу|не надо)[\s!?\.]*", user):
        return False
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and _is_escalation(str(msg.get("content", ""))):
            return True
    return False


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


def write_answer(
    client: httpx.Client,
    messages: list[dict],
    sources: list[Source],
    *,
    fast: bool = False,
) -> str:
    """Текст для судьи и для чата. Правила и форма ответа — в prompt.txt."""
    if not can_call(client, LLM_KEY):
        return FALLBACK
    token_cap = CHAT_MAX_TOKENS if fast else MAX_TOKENS
    payload = {
        "model": LLM_MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": token_cap,
        "messages": build_messages(messages, _context(sources), client_memory=dialog_memory(messages)),
        **completion_extras(),
    }
    last_error: BaseException | None = None
    attempts = 2
    for attempt in range(attempts):
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
                f"LLM попытка {attempt + 1}: {safe_error(exc)}",
                file=sys.stderr,
            )
    if last_error is not None:
        print(f"LLM ответ не получен: {safe_error(last_error)}", file=sys.stderr)
    return FALLBACK


def _last_question_in_answer(answer: str) -> str:
    last = ""
    for match in re.finditer(r"[^.!?\n]*\?", answer or ""):
        last = match.group(0).strip()
    return last


def suggest_replies(client: httpx.Client, answer: str, *, fast: bool = False) -> list[str]:
    """Короткие варианты ответа на последний вопрос ассистента — генерирует LLM."""
    question = _last_question_in_answer(answer)
    if not question or not can_call(client, LLM_KEY):
        return []
    prompt = (
        "Ты подбираешь варианты быстрых ответов для клиента бизнеса.\n"
        "По последнему вопросу консультанта дай 2–3 коротких варианта (на русском).\n"
        "Правила:\n"
        "— только ответы, которые реально отвечают на ЭТОТ вопрос;\n"
        "— без нумерации и кавычек, до 8 слов в варианте;\n"
        "— один вариант на строку;\n"
        "— если вопрос «есть ли / у вас / имеется» — только «Да», «Нет» или «Пока нет», не периоды суток;\n"
        "— «Днём / Вечером / Круглосуточно» — только если спрашивают, КОГДА больше нагрузка;\n"
        "— диапазоны кВт/МВт — только если спрашивают про присоединённую мощность."
    )
    try:
        result = post(
            client,
            "/chat/completions",
            LLM_KEY,
            {
                "model": LLM_MODEL,
                "temperature": 0.25,
                "max_tokens": 200,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Вопрос консультанта:\n{question}"},
                ],
                **completion_extras(),
            },
        )
        message = result["choices"][0]["message"]
        raw = clean_answer(_llm_message_text(message))
        if not raw:
            alt = message.get("content")
            if isinstance(alt, str):
                raw = alt.strip()
    except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError, OSError) as exc:
        print(f"Подсказки кнопок: {safe_error(exc)}", file=sys.stderr)
        return []
    if not raw:
        return _fallback_suggestions(question)
    items: list[str] = []
    for line in raw.replace(";", "\n").split("\n"):
        line = re.sub(r"^[\d\.\)\-\*•]+\s*", "", line.strip())
        line = line.strip("«»\"' ")
        if not line or len(line) > 72:
            continue
        items.append(line)
    parsed = _dedupe_suggestions(items)[:3]
    return parsed or _fallback_suggestions(question)


def _fallback_suggestions(question: str) -> list[str]:
    """Если модель не вернула текст — простые варианты по формулировке вопроса."""
    q = (question or "").lower().replace("ё", "е")
    if not q:
        return []
    if "почасов" in q or ("учёт" in q and re.search(r"есть|име", q)):
        return ["Да, есть", "Нет", "Планируем внедрить"]
    if re.search(r"есть ли|имеется|имеет ли|у вас", q):
        return ["Да", "Нет", "Не уверен"]
    if re.search(r"когда|в какое время", q) and re.search(r"нагруз|потреб|пик|больше", q):
        return ["Днём", "Вечером", "Круглосуточно"]
    if "ценов" in q and "категор" in q:
        return ["1–2", "3–4", "5–6", "Не знаю"]
    if re.search(r"мощност|присоедин", q):
        return ["Меньше 750 кВт", "750 кВт – 20 МВт", "Больше 20 МВт"]
    return []


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
    fast: bool = False,
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
        sources = (
            retrieve(question, chunks, client=client, facts=facts, fast=fast) if question else []
        )
        ready = client_is_ready(question)
        weak = bool(question) and retrieval_is_weak(question, facts, chunks) and not ready
        suggestions: list[str] = []
        if not question or not can_call(client, LLM_KEY):
            text = FALLBACK
        elif weak and not _user_rejects_escalation(prepared):
            text = CLARIFY
            suggestions = list(TASK_BUTTONS)
        else:
            text = write_answer(client, prepared, sources, fast=fast)
            if _is_escalation(text) and _user_rejects_escalation(prepared):
                text = write_answer(client, prepared, sources, fast=False)
        text = normalize_answer(text, preserve_lines=chat_format)
        suggestions = _dedupe_suggestions(suggestions)
        lead = _lead_for(prepared, sources)
        _remember(key, text, sources, suggestions, lead)
        return ConsultResult(text=text, sources=sources, lead=lead, suggestions=suggestions)
    finally:
        if own_client:
            client.close()
