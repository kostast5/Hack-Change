"""Сабмит МТС EnergyTool: RAG-консультант (роль: Поиск + общая consult)."""
import csv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from consult import consult


def env(name, default=""):
    value = os.getenv(name, "").strip()
    return default if not value or value == name else value


def number(name, default, lower, upper, kind=int):
    try:
        return max(lower, min(upper, kind(env(name))))
    except ValueError:
        return default


DATA_DIR = Path(env("DATA_DIR", "data"))
MAX_WORKERS = number("MAX_WORKERS", 3, 1, 8)
FALLBACK = "Не могу ответить по доступным фрагментам базы знаний."


def find_file(*names):
    for root in (DATA_DIR, Path(__file__).resolve().parent / DATA_DIR, Path.cwd()):
        for name in names:
            path = root / name
            if path.is_file():
                return path
    raise FileNotFoundError(f"Не найдены файлы: {names}")


def main():
    questions_path = find_file("questions.csv", "train.csv")
    with questions_path.open(encoding="utf-8-sig", newline="") as f:
        questions = [(str(row["id"]).strip(), str(row["question"])) for row in csv.DictReader(f)]
    print(f"Вопросов: {len(questions)}", flush=True)

    answers = [FALLBACK] * len(questions)

    def work(i, qid, question):
        try:
            text, sources, draft = consult(question)
            if not text or not text.strip():
                text = FALLBACK
            return i, " ".join(text.split())
        except Exception as exc:
            print(f"Вопрос {i + 1}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return i, FALLBACK

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(work, i, qid, question) for i, (qid, question) in enumerate(questions)]
        for future in as_completed(futures):
            i, answer = future.result()
            answers[i] = answer

    with open("submission.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writerow(["id", "answer"])
        writer.writerows((qid, answers[i]) for i, (qid, _) in enumerate(questions))
    print(f"Готов submission.csv: {len(questions)} ответов", flush=True)


if __name__ == "__main__":
    main()
