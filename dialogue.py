"""История диалога внутри одного question. Между разными id памяти нет."""

import re


_TURN = re.compile(r"(?m)^\s*(Пользователь|Ассистент)\s*:\s*")


def parse_dialogue(text: str) -> list[dict]:
    """Строки «Пользователь:» и «Ассистент:» -> список {role, content}.

    Если меток нет, весь текст — одна реплика пользователя.
    """
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return [{"role": "user", "content": ""}]
    marks = list(_TURN.finditer(raw))
    if not marks:
        return [{"role": "user", "content": " ".join(raw.split())}]
    messages = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(raw)
        content = " ".join(raw[mark.end() : end].split())
        if not content:
            continue
        role = "user" if mark.group(1) == "Пользователь" else "assistant"
        messages.append({"role": role, "content": content})
    if not messages:
        return [{"role": "user", "content": " ".join(raw.split())}]
    return messages


def normalize_messages(messages) -> list[dict]:
    if isinstance(messages, str):
        return parse_dialogue(messages)
    clean = []
    for item in messages or []:
        role = str(item.get("role", "user"))
        if role not in ("user", "assistant"):
            role = "user"
        content = " ".join(str(item.get("content", "")).split())
        if content or role == "user":
            clean.append({"role": role, "content": content})
    if not clean:
        return [{"role": "user", "content": ""}]
    return clean


def last_user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message["role"] == "user" and message["content"]:
            return message["content"]
    return ""


def prior_user_text(messages: list[dict]) -> str:
    """Факты из предыдущих реплик пользователя, без ответов ассистента."""
    said = [message["content"] for message in messages if message["role"] == "user" and message["content"]]
    if len(said) <= 1:
        return ""
    return " ".join(said[:-1])
