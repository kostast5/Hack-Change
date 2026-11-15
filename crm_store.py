"""Локальный список сессий и заявок для страницы менеджера. Не CRM МТС."""

import json
import threading
import time
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "out" / "crm.json"
_lock = threading.Lock()


def _load() -> dict:
    if not _PATH.is_file():
        return {"sessions": {}}
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"sessions": {}}
    if not isinstance(data, dict):
        return {"sessions": {}}
    sessions = data.get("sessions")
    if not isinstance(sessions, dict):
        data["sessions"] = {}
    return data


def _save(data: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = _PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temporary.replace(_PATH)


def _messages(raw) -> list[dict]:
    cleaned = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in ("user", "assistant"):
            continue
        content = " ".join(str(item.get("content", "")).split())
        if content:
            cleaned.append({"role": role, "content": content[:8000]})
        if len(cleaned) >= 40:
            break
    return cleaned


def _lead(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    fio = str(raw.get("fio") or raw.get("full_name") or "")[:200]
    company = str(raw.get("company") or "")[:200]
    summary = str(raw.get("summary") or "")[:4000]
    if fio and "имя не указано" in summary:
        summary = summary.replace("имя не указано", fio, 1)
    if company and "компания не названа" in summary:
        summary = summary.replace("компания не названа", company, 1)
    lead = {
        "fio": fio,
        "phone": str(raw.get("phone") or "")[:40],
        "company": company,
        "summary": summary,
        "sentAt": raw.get("sentAt") or None,
    }
    if not any(lead[key] for key in ("fio", "phone", "company", "summary")):
        return None
    return lead


def upsert_sessions(sessions: list) -> None:
    if not isinstance(sessions, list):
        return
    with _lock:
        data = _load()
        bucket = data.setdefault("sessions", {})
        for item in sessions:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("id") or "").strip()
            if not sid:
                continue
            prev = bucket.get(sid) if isinstance(bucket.get(sid), dict) else {}
            lead = _lead(item.get("lead")) or _lead(prev.get("lead"))
            state = str(item.get("leadState") or "")
            if state not in ("none", "draft", "sent"):
                state = "sent" if lead and lead.get("sentAt") else "none"
            bucket[sid] = {
                "id": sid,
                "title": str(item.get("title") or "Диалог")[:160],
                "ts": int(item.get("ts") or prev.get("ts") or time.time() * 1000),
                "leadState": state,
                "messages": _messages(item.get("messages")) or _messages(prev.get("messages")),
                "lead": lead,
            }
        _save(data)


def save_lead(body: dict) -> None:
    if not isinstance(body, dict):
        return
    sid = str(body.get("sessionId") or body.get("id") or "").strip()
    if not sid:
        return
    sent = _lead(body) or {}
    sent["sentAt"] = int(time.time() * 1000)
    with _lock:
        data = _load()
        bucket = data.setdefault("sessions", {})
        prev = bucket.get(sid) if isinstance(bucket.get(sid), dict) else {}
        bucket[sid] = {
            "id": sid,
            "title": str(body.get("title") or prev.get("title") or "Диалог")[:160],
            "ts": int(body.get("ts") or prev.get("ts") or sent["sentAt"]),
            "leadState": "sent",
            "messages": _messages(body.get("messages")) or _messages(prev.get("messages")),
            "lead": sent,
        }
        _save(data)


def list_sessions() -> list[dict]:
    with _lock:
        data = _load()
    items = [item for item in data.get("sessions", {}).values() if isinstance(item, dict)]
    items.sort(key=lambda item: item.get("ts") or 0, reverse=True)
    return items


def clear_sessions() -> None:
    """Очистить локальный список диалогов (out/crm.json)."""
    with _lock:
        _save({"sessions": {}})
