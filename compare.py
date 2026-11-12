"""Сверка ответов бота с образцами перед сабмитом.

Запуск (из папки hack, когда solution.py уже создал submission.csv):
    python3 compare.py

Результат — файл сверка.txt: вопрос, образец и ответ бота рядом.
"""

import csv

# Эти вопросы стоят в prompt.txt как примеры — по ним качество не оцениваем.
EXAMPLES_IN_PROMPT = {"4", "9", "18"}


def read_csv(path, column):
    """CSV → словарь {id: текст из нужной колонки}."""
    with open(path, encoding="utf-8-sig") as f:
        return {row["id"]: row[column] for row in csv.DictReader(f)}


def main():
    questions = read_csv("demo_questions.csv", "question")
    golden = read_csv("demo_output.csv", "answer")
    bot = read_csv("submission.csv", "answer")

    lines = []
    for qid in questions:
        mark = "  (пример в промпте — не считаем)" if qid in EXAMPLES_IN_PROMPT else ""
        bot_answer = bot.get(qid, "НЕТ ОТВЕТА")
        lines.append(f"===== Вопрос {qid}{mark} =====")
        lines.append(questions[qid].strip())
        lines.append("")
        lines.append(f"ОБРАЗЕЦ ({len(golden.get(qid, '').split())} слов):")
        lines.append(golden.get(qid, "—"))
        lines.append("")
        lines.append(f"БОТ ({len(bot_answer.split())} слов):")
        lines.append(bot_answer)
        lines.append("")
        lines.append("Какие факты потерялись: ")
        lines.append("")

    with open("сверка.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    missing = [qid for qid in questions if qid not in bot]
    print(f"Готово: сверка.txt ({len(questions)} вопросов).")
    if missing:
        print("Нет ответа на вопросы:", ", ".join(missing))


if __name__ == "__main__":
    main()
