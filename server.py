"""Тонкий веб-сервер: отдаёт интерфейс и вызывает тот же consult(), что и судья.

Запуск из корня: uvicorn server:app --host 0.0.0.0 --port 8000
В ZIP платформы этот файл не входит: судья запускает solution.py.
"""

import dataclasses
import os
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
_materials = BASE_DIR / "_materials" / "knowledge-base.zip"
if not os.getenv("DATA_DIR", "").strip() and _materials.is_file():
    os.environ["DATA_DIR"] = str(BASE_DIR / "_materials")

from dialogue import last_user_text, normalize_messages
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import crm_store
from flow import cache_clear

try:
    import solution
    IMPORT_ERROR = None
except Exception as exc:
    solution = None
    IMPORT_ERROR = exc

LEAD_FIELDS = ("fio", "phone", "company", "summary")
QUOTE_LIMIT = 300

app = FastAPI()

_chunks = None
_chunks_lock = threading.Lock()


class ConsultRequest(BaseModel):
    messages: list[dict]


def get_chunks():
    """База знаний грузится один раз, при первом вопросе."""
    global _chunks
    with _chunks_lock:
        if _chunks is None:
            _chunks = solution.load_chunks(solution.find_file(*solution.KB_NAMES))
        return _chunks


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
    """Карточка заявки только после согласия клиента. Пустой черновик — это null."""
    lead = getattr(result, "lead", None)
    if not lead:
        return None
    if dataclasses.is_dataclass(lead):
        data = dataclasses.asdict(lead)
    elif isinstance(lead, dict):
        data = dict(lead)
    else:
        data = {
            key: getattr(lead, key, "")
            for key in ("ready", "full_name", "fio", "phone", "company", "summary")
        }
    payload = {
        "fio": str(data.get("fio") or data.get("full_name") or ""),
        "phone": str(data.get("phone") or ""),
        "company": str(data.get("company") or ""),
        "summary": str(data.get("summary") or ""),
    }
    ready = data.get("ready", None)
    if ready is False:
        return None
    if ready is None and not any(payload.values()):
        return None
    return {key: payload[key] for key in LEAD_FIELDS}


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "index.html")


@app.post("/api/consult")
def api_consult(req: ConsultRequest):
    if solution is None:
        raise HTTPException(status_code=503, detail=f"solution.py не подключён: {IMPORT_ERROR}")
    messages = normalize_messages(req.messages)
    if not last_user_text(messages):
        raise HTTPException(status_code=400, detail="Нет текста сообщения")
    client = solution.make_client()
    try:
        result = solution.consult(
            messages,
            client=client,
            chunks=get_chunks(),
            chat_format=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=solution.safe_error(exc))
    finally:
        client.close()
    return {
        "answer": result.text,
        "sources": [to_source(source) for source in result.sources],
        "lead": to_lead(result),
        "suggestions": [str(item) for item in getattr(result, "suggestions", []) or [] if str(item).strip()],
        "cached": bool(getattr(result, "cached", False)),
    }


@app.post("/api/lead")
def api_lead(body: dict):
    crm_store.save_lead(body)
    return {"ok": True}


@app.post("/api/reset")
def api_reset():
    """Локально: сброс кэша LLM и сохранённых сессий при перезагрузке чата."""
    cache_clear()
    crm_store.clear_sessions()
    return {"ok": True}


@app.get("/api/sessions")
def api_sessions():
    return {"sessions": crm_store.list_sessions()}


@app.post("/api/sessions")
def api_save_sessions(body: dict):
    crm_store.upsert_sessions(body.get("sessions") if isinstance(body, dict) else [])
    return {"ok": True}


@app.get("/manager")
def manager_page():
    return FileResponse(BASE_DIR / "manager.html")


@app.get("/site")
def site_page():
    return FileResponse(BASE_DIR / "site.html")


@app.get("/widget.js")
def widget_script():
    return FileResponse(BASE_DIR / "widget.js", media_type="application/javascript")


app.mount("/src", StaticFiles(directory=BASE_DIR / "src"), name="src")
app.mount("/styles", StaticFiles(directory=BASE_DIR / "styles"), name="styles")
