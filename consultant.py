"""Часть «Консультант»: подготовка переписки и сообщений для нейросети.

Здесь нет поиска и нет обращения к нейросети — это делают другие части.
Этот файл умеет:
  1. parse_dialog    — разрезать переписку на сообщения;
  2. search_query    — подсказать «Поиску», что искать;
  3. build_messages  — собрать промпт + найденный текст + переписку;
  4. clean_answer    — почистить ответ нейросети перед записью в CSV.
"""

import re
from pathlib import Path

PROMPT_FILE = Path(__file__).resolve().parent / "prompt.txt"

USER_LABEL = "Пользователь:"
ASSISTANT_LABEL = "Ассистент:"


def parse_dialog(text):
    """Строка вопроса → список сообщений [{"role": ..., "content": ...}]."""
    messages = []

    for line in text.split("\n"):
        line = line.strip()
        if line == "":
            continue

        if line.startswith(USER_LABEL):
            content = line[len(USER_LABEL):].strip()
            messages.append({"role": "user", "content": content})

        elif line.startswith(ASSISTANT_LABEL):
            content = line[len(ASSISTANT_LABEL):].strip()
            messages.append({"role": "assistant", "content": content})

        elif len(messages) == 0:
            # Обычный вопрос без подписей.
            messages.append({"role": "user", "content": line})

        else:
            # Продолжение предыдущей реплики на новой строке.
            messages[-1]["content"] += " " + line

    return messages


def search_query(messages):
    """Текст для поиска по базе: последняя реплика клиента + его прошлые реплики.

    Реплики бота не берём: в них нет фактов о клиенте.
    """
    user_texts = [m["content"] for m in messages if m["role"] == "user"]
    if not user_texts:
        return ""
    last = user_texts[-1]
    earlier = user_texts[:-1]
    return " ".join([last] + earlier)


def load_prompt(path=PROMPT_FILE):
    """prompt.txt → (правила, шаблон). Делим файл по строке '---'."""
    text = Path(path).read_text(encoding="utf-8")
    rules, template = text.split("\n---\n", 1)
    return rules.strip(), template.strip()


def build_messages(messages, context, path=PROMPT_FILE):
    """Собирает то, что уйдёт нейросети.

    messages — результат parse_dialog;
    context  — текст, который нашёл «Поиск» (может быть пустым).
    """
    rules, template = load_prompt(path)

    history = messages[:-1]          # всё, кроме последней реплики
    last_question = messages[-1]["content"] if messages else ""

    if not context.strip():
        context = "(в базе знаний ничего не найдено)"

    # replace, а не format: в тексте базы могут встретиться фигурные скобки.
    final_text = template.replace("{context}", context).replace("{question}", last_question)

    result = [{"role": "system", "content": rules}]
    result += history
    result.append({"role": "user", "content": final_text})
    return result


THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def clean_answer(text):
    """Убирает рассуждения <think>…</think> и лишние пробелы и переносы."""
    text = THINK_BLOCK.sub("", text or "")
    if "</think>" in text:           # бывает, что открывающего тега нет
        text = text.split("</think>")[-1]
    return " ".join(text.split())


if __name__ == "__main__":
    # Проверка без нейросети: смотрим, как разбираются demo-вопросы.
    import csv

    with open("demo_questions.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        msgs = parse_dialog(row["question"])
        roles = " → ".join(m["role"] for m in msgs)
        print(f'{row["id"]:>2}: {len(msgs)} сообщ. ({roles})')

    print("\n=== Пример: что уйдёт нейросети для вопроса 17 ===")
    msgs = parse_dialog(rows[16]["question"])
    print("Искать в базе:", search_query(msgs))
    for m in build_messages(msgs, "ТУТ БУДЕТ ТЕКСТ ИЗ БАЗЫ"):
        preview = m["content"] if m["role"] != "system" else m["content"][:60] + "…"
        print(f'[{m["role"]}] {preview}')

    print("\n=== Проверка clean_answer ===")
    print(clean_answer("<think>Думаю...\nдолго</think>\n\nДа, можно.\nКакой регион?"))
