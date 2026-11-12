"""Точка входа платформы: вопросы, пул, submission.csv.

Поиск живёт в retrieve.rank_chunks, текст ответа — в consult.write_answer.
В CSV попадает только текст. Источники и заявка остаются в ConsultResult.
"""

import csv
import io
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from chunks import load_chunks
from config import (
    ANSWER_LIMIT,
    BASE_URL,
    CHUNKER,
    FALLBACK,
    KB_NAMES,
    LLM_KEY,
    LLM_MODEL,
    MAX_WORKERS,
    QUESTION_NAMES,
    RUN_BUDGET_SEC,
    find_file,
    submission_path,
)
from consult import consult, normalize_answer
from contract import Source
from dialogue import parse_dialogue
from llm import make_client, safe_error


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except Exception:
            pass


def read_questions(path: Path) -> list[tuple[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        if "id" not in fields or "question" not in fields:
            raise ValueError("Нужны колонки id и question")
        rows = []
        for row in reader:
            qid = "" if row.get("id") is None else str(row.get("id")).strip()
            question = "" if row.get("question") is None else str(row.get("question"))
            if not qid:
                raise ValueError("Во входном файле есть пустой id")
            rows.append((qid, question))
    if not rows:
        raise ValueError("Во входном файле нет вопросов")
    return rows


def unique_questions(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    kept = []
    for qid, question in rows:
        if qid in seen:
            print(f"Повтор id {qid}: в расчёт пойдёт первое вхождение", file=sys.stderr)
            continue
        seen.add(qid)
        kept.append((qid, question))
    return kept


def format_sources(sources: list[Source]) -> str:
    if not sources:
        return "нет фрагмента"
    parts = [f"{source.path} | {source.heading} | {source.score:.2f}" for source in sources[:2]]
    return " || ".join(parts)


def run_pool(questions, chunks, answers: list[str], notes: list[str]) -> None:
    deadline = time.monotonic() + RUN_BUDGET_SEC
    late = False
    lock = threading.Lock()
    local = threading.local()
    clients: list = []

    def client_for_thread():
        client = getattr(local, "client", None)
        if client is None:
            client = make_client()
            local.client = client
            with lock:
                clients.append(client)
        return client

    def work(index: int, question: str):
        nonlocal late
        if time.monotonic() > deadline:
            with lock:
                if not late:
                    print(
                        "Бюджет времени исчерпан, остальные ответы — заглушка",
                        file=sys.stderr,
                        flush=True,
                    )
                    late = True
            return index, FALLBACK, []
        try:
            result = consult(parse_dialogue(question), client=client_for_thread(), chunks=chunks)
            return index, result.text, result.sources
        except Exception as exc:
            print(f"Вопрос {questions[index][0]}: {safe_error(exc)}", file=sys.stderr, flush=True)
            return index, FALLBACK, []

    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = [pool.submit(work, index, question) for index, (_, question) in enumerate(questions)]
            done = 0
            total = len(questions)
            for future in as_completed(futures):
                index, text, sources = future.result()
                answers[index] = normalize_answer(text)
                notes[index] = format_sources(sources)
                done += 1
                print(f"[{done}/{total}] {questions[index][0]} {notes[index]}", flush=True)
    finally:
        for client in clients:
            client.close()


def write_submission(questions, answers: list[str], path: Path | None = None) -> Path:
    path = path or submission_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writerow(["id", "answer"])
        for (qid, _), answer in zip(questions, answers):
            writer.writerow([qid, normalize_answer(answer)])
    return path


def validate_submission(path: Path, expected_ids: list[str]) -> list[str]:
    errors = []
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        errors.append("UTF-8 BOM не нужен")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ["файл не в UTF-8"]
    if "\r" in text:
        errors.append("в файле есть перевод строки Windows (CR)")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return errors + ["файл пустой"]
    if rows[0] != ["id", "answer"]:
        errors.append(f"заголовок {rows[0]!r}, нужен id,answer")
    body = rows[1:]
    if len(body) != len(expected_ids):
        errors.append(f"строк {len(body)}, ожидалось {len(expected_ids)}")
    seen: set[str] = set()
    for index, row in enumerate(body):
        if len(row) != 2:
            errors.append(f"строка {index + 2}: колонок {len(row)}")
            continue
        qid, answer = row
        if index < len(expected_ids) and qid != expected_ids[index]:
            errors.append(f"строка {index + 2}: id {qid!r} вместо {expected_ids[index]!r}")
        if qid in seen:
            errors.append(f"повтор id {qid}")
        seen.add(qid)
        if not answer.strip():
            errors.append(f"пустой ответ у id {qid}")
        if "\n" in answer or "\r" in answer:
            errors.append(f"перенос внутри ответа id {qid}")
        if len(answer) > ANSWER_LIMIT:
            errors.append(f"ответ id {qid} длиннее {ANSWER_LIMIT}")
    return errors


def main() -> int:
    _configure_stdio()
    questions_path = find_file(*QUESTION_NAMES)
    kb_path = find_file(*KB_NAMES)
    questions = unique_questions(read_questions(questions_path))
    chunks = load_chunks(kb_path)
    llm_on = bool(BASE_URL and LLM_KEY)
    print(
        f"Вопросов: {len(questions)}; фрагментов: {len(chunks)}; "
        f"LLM: {'да' if llm_on else 'нет, в CSV будет заглушка'}; "
        f"модель: {LLM_MODEL}; workers: {MAX_WORKERS}; chunker: {CHUNKER}",
        flush=True,
    )
    print(f"Вход: {questions_path}", flush=True)
    print(f"База: {kb_path}", flush=True)
    answers = [FALLBACK] * len(questions)
    notes = ["нет фрагмента"] * len(questions)
    failed = False
    try:
        run_pool(questions, chunks, answers, notes)
    except KeyboardInterrupt:
        failed = True
        print("Остановлено, записываю уже готовые ответы", file=sys.stderr, flush=True)
    except Exception as exc:
        failed = True
        print(safe_error(exc), file=sys.stderr, flush=True)
    path = write_submission(questions, answers)
    errors = validate_submission(path, [qid for qid, _ in questions])
    for error in errors:
        print(error, file=sys.stderr, flush=True)
    stubs = sum(1 for answer in answers if answer == FALLBACK)
    print(f"Готов {path}: {len(questions)} ответов, заглушек: {stubs}", flush=True)
    if errors or failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
