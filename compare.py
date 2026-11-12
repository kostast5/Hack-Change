# Сверка перед сабмитом: кладём рядом вопрос, образец и ответ бота.
# Запуск: python3 compare.py (рядом должны быть demo_questions.csv,
# demo_output.csv и submission.csv). Результат - файл сверка.txt.

import csv

# эти вопросы стоят примерами в prompt.txt, по ним качество не смотрим
EXAMPLES_IN_PROMPT = {"4", "9", "18"}


# csv -> словарь {id: текст}
def read_csv(path, column):
    with open(path, encoding="utf-8-sig") as f:
        return {row["id"]: row[column] for row in csv.DictReader(f)}


def main():
    questions = read_csv("demo_questions.csv", "question")
    golden = read_csv("demo_output.csv", "answer")
    bot = read_csv("submission.csv", "answer")

    lines = []
    for qid in questions:
        mark = "  (пример в промпте, не считаем)" if qid in EXAMPLES_IN_PROMPT else ""
        bot_answer = bot.get(qid, "НЕТ ОТВЕТА")
        lines.append(f"===== Вопрос {qid}{mark} =====")
        lines.append(questions[qid].strip())
        lines.append("")
        lines.append(f"ОБРАЗЕЦ ({len(golden.get(qid, '').split())} слов):")
        lines.append(golden.get(qid, "-"))
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
