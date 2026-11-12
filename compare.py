# Сверка перед сабмитом: кладём рядом вопрос, образец и ответ бота.
# Запуск из корня проекта: python compare.py
# Результат — файл сверка.txt. В ZIP платформы этот скрипт не входит.

import csv
from pathlib import Path

# эти вопросы стоят примерами в prompt.txt, по ним качество не смотрим
EXAMPLES_IN_PROMPT = {"4", "9", "18"}

ROOT = Path(__file__).resolve().parent


def locate(name: str) -> Path:
    for folder in (ROOT, ROOT / "_materials", ROOT / "out"):
        path = folder / name
        if path.is_file():
            return path
    raise SystemExit(f"Нет файла {name}")


# csv -> словарь {id: текст}
def read_csv(path, column):
    with open(path, encoding="utf-8-sig") as f:
        return {row["id"]: row[column] for row in csv.DictReader(f)}


def main():
    questions = read_csv(locate("demo_questions.csv"), "question")
    golden = read_csv(locate("demo_output.csv"), "answer")
    bot = read_csv(locate("submission.csv"), "answer")

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

    destination = ROOT / "сверка.txt"
    destination.write_text("\n".join(lines), encoding="utf-8")

    missing = [qid for qid in questions if qid not in bot]
    print(f"Готово: {destination} ({len(questions)} вопросов).")
    if missing:
        print("Нет ответа на вопросы:", ", ".join(missing))


if __name__ == "__main__":
    main()
