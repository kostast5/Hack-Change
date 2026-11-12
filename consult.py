"""consult(messages) — общая точка для solution.py и веб-чата.

Роль «Консультант» меняет SYSTEM_PROMPT и write_answer.
Каркас не придумывает, какие уточняющие вопросы задавать.
Заявка остаётся пустой: её включает консультант, когда клиент сам согласен.
"""

import sys

import httpx

from config import ANSWER_LIMIT, FALLBACK, LLM_KEY, LLM_MODEL, MAX_TOKENS, TEMPERATURE
from contract import ConsultResult, LeadDraft, Source
from chunks import Chunk, load_chunks
from dialogue import last_user_text, normalize_messages, prior_user_text
from llm import can_call, make_client, post, safe_error
from retrieve import retrieve

SYSTEM_PROMPT = (
    "Ты консультант МТС EnergyTool. Ответь по-русски на последнюю реплику пользователя. "
    "Опирайся только на фрагменты базы знаний. Не добавляй факты, которых во фрагментах нет. "
    "Если во фрагментах нет ответа, прямо скажи об этом и предложи связаться со специалистом. "
    "Не запрашивай фамилию, телефон и название компании. "
    "Пиши кратко, обычно до 150 слов, одним абзацем."
)


def normalize_answer(text: str) -> str:
    flat = " ".join((text or "").split())
    if not flat:
        return FALLBACK
    if len(flat) > ANSWER_LIMIT:
        flat = flat[:ANSWER_LIMIT].rstrip()
    return flat or FALLBACK


def _dialogue(messages: list[dict]) -> str:
    lines = []
    for message in messages:
        speaker = "Пользователь" if message["role"] == "user" else "Ассистент"
        if message["content"]:
            lines.append(f"{speaker}: {message['content']}")
    return "\n".join(lines)


def _fragments(sources: list[Source]) -> str:
    blocks = []
    for index, source in enumerate(sources, start=1):
        blocks.append(f"[{index}] {source.path} — {source.heading}\n{source.quote}")
    return "\n\n".join(blocks)


def write_answer(client: httpx.Client, messages: list[dict], sources: list[Source]) -> str:
    """Текст для судьи и для чата. Здесь меняется промпт консультанта."""
    if not can_call(client, LLM_KEY):
        return FALLBACK
    payload = {
        "model": LLM_MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Диалог:\n"
                    + _dialogue(messages)
                    + "\n\nОтветь на последнюю реплику пользователя.\n\nФрагменты базы знаний:\n"
                    + _fragments(sources)
                ),
            },
        ],
    }
    for attempt in range(2):
        try:
            result = post(client, "/chat/completions", LLM_KEY, payload)
            content = result["choices"][0]["message"].get("content") or ""
            if isinstance(content, list):
                content = " ".join(str(part) for part in content)
            if isinstance(content, str) and content.strip():
                return content
            raise ValueError("LLM вернула пустой ответ")
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError) as exc:
            print(f"LLM попытка {attempt + 1}: {safe_error(exc)}", file=sys.stderr)
    return FALLBACK


def consult(messages, client: httpx.Client | None = None, chunks: list[Chunk] | None = None) -> ConsultResult:
    """Возвращает текст, источники и пустой черновик заявки."""
    prepared = normalize_messages(messages)
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
        if not question or not sources:
            text = FALLBACK
        else:
            text = write_answer(client, prepared, sources)
        return ConsultResult(text=normalize_answer(text), sources=sources, lead=LeadDraft())
    finally:
        if own_client:
            client.close()
