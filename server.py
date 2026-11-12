"""Тонкий веб-сервер: отдаёт интерфейс и вызывает consult() из solution.py.
Запуск: uvicorn server:app --port 8000

solution.py не изменён: сервер берёт из него то же, что использует его main():
load_chunks, make_client, parse_dialogue, consult, normalize_answer.
"""
import dataclasses
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    import solution  # код команды: поиск по базе + генерация ответа
except ImportError as exc:  # нет solution.py или его модулей (chunks, config, consult, ...)
    solution = None
    IMPORT_ERROR = exc

BASE_DIR = Path(__file__).resolve().parent
LEAD_FIELDS = ("fio", "phone", "company", "summary")
QUOTE_LIMIT = 300

app = FastAPI()

_chunks = None
_chunks_lock = threading.Lock()


class ConsultRequest(BaseModel):
    messages: list[dict]  # [{"role": "user"|"assistant", "content": "..."}]


def get_chunks():
    """База знаний грузится один раз, при первом вопросе."""
    global _chunks
    with _chunks_lock:
        if _chunks is None:
            _chunks = solution.load_chunks(solution.find_file(*solution.KB_NAMES))
        return _chunks


def to_dialogue(messages: list[dict]) -> str:
    """История чата -> строки «Пользователь:» / «Ассистент:», как ждёт parse_dialogue()."""
    names = {"user": "Пользователь", "assistant": "Ассистент"}
    lines = [
        f"{names[m['role']]}: {str(m.get('content', '')).strip()}"
        for m in messages
        if m.get("role") in names and str(m.get("content", "")).strip()
    ]
    return "\n".join(lines)


def to_source(source) -> dict:
    quote = getattr(source, "quote", None) or getattr(source, "text", None) or ""
    score = getattr(source, "score", None)
    return {
        "path": getattr(source, "path", ""),
        "title": getattr(source, "heading", None) or getattr(source, "title", "") or "",
        "quote": str(quote)[:QUOTE_LIMIT],
        "score": float(score) if score is not None else None,
    }


def to_lead(result):
    """Черновик заявки из ConsultResult; None, пока клиент не согласился оставить контакт."""
    lead = getattr(result, "lead", None)
    if not lead:
        return None
    if dataclasses.is_dataclass(lead):
        lead = dataclasses.asdict(lead)
    elif not isinstance(lead, dict):
        lead = {k: getattr(lead, k, "") for k in LEAD_FIELDS}
    return {k: str(lead.get(k) or "") for k in LEAD_FIELDS}


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "index.html")


@app.post("/api/consult")
def api_consult(req: ConsultRequest):
    if solution is None:
        raise HTTPException(status_code=503, detail=f"solution.py не подключён: {IMPORT_ERROR}")
    client = solution.make_client()
    try:
        result = solution.consult(
            solution.parse_dialogue(to_dialogue(req.messages)),
            client=client,
            chunks=get_chunks(),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=solution.safe_error(exc))
    finally:
        client.close()
    return {
        "answer": solution.normalize_answer(result.text),
        "sources": [to_source(s) for s in result.sources],
        "lead": to_lead(result),
    }


@app.post("/api/lead")
def api_lead(body: dict):
    return {"ok": True}  # реальную CRM не подключаем


app.mount("/src", StaticFiles(directory=BASE_DIR / "src"), name="src")
app.mount("/styles", StaticFiles(directory=BASE_DIR / "styles"), name="styles")
