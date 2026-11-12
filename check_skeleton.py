"""Офлайн-проверка каркаса перед сабмитом. Сеть не вызывает."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("DATA_DIR", str(ROOT / "_materials"))
os.environ["ENERGYTOOL_SKIP_DOTENV"] = "1"
for _name in (
    "LLM_API_KEY",
    "OPENAI_API_KEY",
    "LLM_BASE_URL",
    "OPENAI_BASE_URL",
    "BASE_URL",
    "EMBEDDER_API_KEY",
    "RERANKER_API_KEY",
):
    os.environ.pop(_name, None)

from chunks import load_chunks
from config import FALLBACK
from consult import consult, normalize_answer
from dialogue import last_user_text, parse_dialogue, prior_user_text
from solution import read_questions, validate_submission, write_submission


EXPECTED_LAST = {
    "14": "А обычная сетевая станция с вечерней нагрузкой вообще имеет смысл?",
    "15": "Кто-то присылает фото, а по некоторым ходит техник. С чего нам начать?",
    "16": "Примерно за два года. Таких данных хватит, чтобы начать?",
    "17": "Кажется, четвёртая. Что вообще стоит проверить в счёте?",
    "18": "Я пока не готов оставлять телефон. Можете объяснить, что понадобится для оценки?",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def check_dialogue() -> list[tuple[str, str]]:
    path = ROOT / "_materials" / "demo_questions.csv"
    rows = read_questions(path)
    if len(rows) != 18:
        fail(f"В демо {len(rows)} вопросов, ожидалось 18")
    by_id = dict(rows)
    for qid, expected in EXPECTED_LAST.items():
        messages = parse_dialogue(by_id[qid])
        if last_user_text(messages) != expected:
            fail(f"id {qid}: последняя реплика {last_user_text(messages)!r}")
        if messages[-1]["role"] != "user":
            fail(f"id {qid}: последняя реплика не пользователя")
    roles = [item["role"] for item in parse_dialogue(by_id["14"])]
    if roles != ["user", "assistant", "user", "assistant", "user"]:
        fail(f"id 14: роли {roles}")
    single = parse_dialogue(by_id["1"])
    if len(single) != 1 or single[0]["role"] != "user":
        fail("id 1 должен быть одной репликой пользователя")
    facts = prior_user_text(parse_dialogue(by_id["18"])).lower()
    if "склад" not in facts or "сорока" not in facts:
        fail("id 18: в фактах диалога нет складов")
    return rows


def check_chunks():
    path = ROOT / "_materials" / "knowledge-base.zip"
    chunks = load_chunks(path)
    if len(chunks) < 40:
        fail(f"Слишком мало фрагментов: {len(chunks)}")
    paths = {chunk.path for chunk in chunks}
    if "20-products/23-solar.md" not in paths:
        fail("В нарезке нет 20-products/23-solar.md")
    if not any(len(chunk.text) > 500 for chunk in chunks):
        fail("Все фрагменты короткие: нарезка похожа на обрезку начала файла")
    if not any(chunk.heading.endswith("Размещение") for chunk in chunks if chunk.path.endswith("23-solar.md")):
        fail("У солнечной станции нет раздела «Размещение»")
    return chunks


def check_consult(rows, chunks) -> None:
    by_id = dict(rows)
    result = consult(parse_dialogue(by_id["1"]), client=None, chunks=chunks)
    if result.text != FALLBACK:
        fail("Без ключа LLM ответ должен быть заглушкой")
    if "\n" in result.text or not result.text.strip():
        fail("Текст ответа должен быть одной непустой строкой")
    if result.lead.ready or result.lead.phone or result.lead.full_name or result.lead.company or result.lead.summary:
        fail("Каркас не заполняет заявку")
    if not result.sources or "23-solar.md" not in result.sources[0].path:
        got = result.sources[0].path if result.sources else "пусто"
        fail(f"Вопрос про скаты крыши ушёл не в солнечную станцию: {got}")
    if normalize_answer("первая\nстрока\n\nвторая") != "первая строка вторая":
        fail("Переносы внутри ответа не схлопываются")


def check_csv_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "submission.csv"
        questions = [("1", "a\nb"), ("2", "")]
        write_submission(questions, ["строка\nдва", ""], path)
        errors = validate_submission(path, ["1", "2"])
        if errors:
            fail("; ".join(errors))
        text = path.read_text(encoding="utf-8")
        if "\r" in text or "\n\n" in text.strip():
            fail("CSV записан с лишними переносами")


def report_ranking(rows, chunks) -> None:
    print("Топ фрагмента по демо-вопросам:")
    for qid, question in rows:
        messages = parse_dialogue(question)
        result = consult(messages, client=None, chunks=chunks)
        if result.sources:
            top = result.sources[0]
            place = f"{top.path} | {top.heading}"
        else:
            place = "нет фрагмента"
        print(f"  {qid}: {place}")


def check_existing_submission() -> None:
    import csv
    import io

    candidates = [ROOT / "submission.csv", ROOT / "out" / "submission.csv"]
    path = next((item for item in candidates if item.is_file()), None)
    if path is None:
        print("submission.csv ещё нет — это нормально до первого прогона")
        return
    text = path.read_text(encoding="utf-8")
    parsed = list(csv.reader(io.StringIO(text)))
    ids = [row[0] for row in parsed[1:] if len(row) == 2]
    errors = validate_submission(path, ids)
    if errors:
        fail(f"{path}: " + "; ".join(errors))
    demo_ids = [qid for qid, _ in read_questions(ROOT / "_materials" / "demo_questions.csv")]
    if ids == demo_ids:
        print(f"Формат {path}: {len(ids)} ответов, id совпадают с демо")
    else:
        print(f"Формат {path}: {len(ids)} ответов")


def main() -> int:
    rows = check_dialogue()
    chunks = check_chunks()
    check_consult(rows, chunks)
    check_csv_roundtrip()
    report_ranking(rows, chunks)
    check_existing_submission()
    print(f"Каркас: проверки пройдены, фрагментов: {len(chunks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
