# Часть консультанта: готовим вопрос для нейросети и чистим её ответ.
# Поиск по базе и сам запрос к модели тут не делаются, это в solution.py.
#
# Как подключать в solution.py:
#   messages = parse_dialog(question)
#   context  = <ваш поиск>(search_query(messages))
#   answer   = clean_answer(<запрос к модели>(build_messages(messages, context)))

import os
import sys
import re
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# prompt.txt должен лежать рядом с этим файлом (и в zip тоже в корне)
PROMPT_FILE = Path(__file__).resolve().parent / "prompt.txt"

USER_LABEL = "Пользователь:"
ASSISTANT_LABEL = "Ассистент:"


# Режем вопрос на сообщения. В диалогах (14-18) всё приходит одной строкой
# с подписями "Пользователь:" / "Ассистент:", а модели нужен список ролей.
def parse_dialog(text):
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
            # обычный вопрос без подписей
            messages.append({"role": "user", "content": line})

        else:
            # реплика переносится на новую строку - клеим к предыдущей
            messages[-1]["content"] += " " + line

    return messages


# Что отдавать поиску. Только по последней реплике искать плохо
# (там бывает просто "Кажется, четвёртая"), поэтому добавляем
# прошлые реплики клиента. Реплики бота не берём.
def search_query(messages):
    user_texts = [m["content"] for m in messages if m["role"] == "user"]
    if not user_texts:
        return ""
    last = user_texts[-1]
    earlier = user_texts[:-1]
    return " ".join([last] + earlier)


# Делим prompt.txt по строке "---": сверху правила, снизу шаблон
def load_prompt(path=PROMPT_FILE):
    text = Path(path).read_text(encoding="utf-8")
    rules, template = text.split("\n---\n", 1)
    return rules.strip(), template.strip()


# Собираем сообщения для /chat/completions:
# system - правила, потом старые реплики, в конце текст из базы + последний вопрос
def build_messages(messages, context, path=PROMPT_FILE):
    rules, template = load_prompt(path)

    history = messages[:-1]
    last_question = messages[-1]["content"] if messages else ""

    # если поиск ничего не нашёл, модель должна честно это сказать
    if not context.strip():
        context = "(в базе знаний ничего не найдено)"

    # replace, а не format - в тексте базы могут быть фигурные скобки
    final_text = template.replace("{context}", context).replace("{question}", last_question)

    result = [{"role": "system", "content": rules}]
    result += history
    result.append({"role": "user", "content": final_text})
    return result


THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


# Qwen иногда пишет рассуждения в <think>...</think> - вырезаем.
# Переносы строк тоже убираем, в csv ответ должен быть в одну строку.
def clean_answer(text):
    text = THINK_BLOCK.sub("", text or "")
    if "</think>" in text:  # бывает закрывающий тег без открывающего
        text = text.split("</think>")[-1]
    return " ".join(text.split())


# Быстрая проверка без модели: python3 consultant.py
# (запускать из папки, где лежит demo_questions.csv)
if __name__ == "__main__":
    import csv

    with open("demo_questions.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        msgs = parse_dialog(row["question"])
        roles = " -> ".join(m["role"] for m in msgs)
        print(f'{row["id"]:>2}: {len(msgs)} сообщ. ({roles})')

    print("\nвопрос 17, что уйдёт модели:")
    msgs = parse_dialog(rows[16]["question"])
    print("поиск:", search_query(msgs))
    for m in build_messages(msgs, "ТУТ БУДЕТ ТЕКСТ ИЗ БАЗЫ"):
        preview = m["content"] if m["role"] != "system" else m["content"][:60] + "..."
        print(f'[{m["role"]}] {preview}')

    print("\nclean_answer:")
    print(clean_answer("<think>Думаю...\nдолго</think>\n\nДа, можно.\nКакой регион?"))
