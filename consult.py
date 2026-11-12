"""Общий контракт консультанта: consult(messages) ---> (text, sources, draft)."""
import os
import re
import httpx

from chunking import load_chunks_from_dir
from search import search

_CHUNKS = None


def get_chunks():
    global _CHUNKS
    if _CHUNKS is None:
        data_dir = os.getenv("DATA_DIR", "data")
        from pathlib import Path
        root = Path(data_dir)
        kb = None
        for name in ("knowledge-base.zip", "knowledge_base.zip", "kb.zip"):
            p = root / name
            if p.is_file():
                kb = p
                break
        if kb is not None:
            import tempfile, zipfile
            tmp = Path(tempfile.mkdtemp())
            with zipfile.ZipFile(kb) as z:
                z.extractall(tmp)
            root = tmp
        _CHUNKS = load_chunks_from_dir(str(root))
    return _CHUNKS


def parse_history(messages) -> tuple[str, str]:
    if isinstance(messages, str):
        text = messages.strip()
        if "Пользователь:" in text or "Ассистент:" in text:
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            user_msgs = []
            history_lines = []
            for ln in lines:
                if ln.startswith("Пользователь:"):
                    content = ln[len("Пользователь:"):].strip()
                    role = "user"
                elif ln.startswith("Ассистент:"):
                    content = ln[len("Ассистент:"):].strip()
                    role = "assistant"
                else:
                    if history_lines:
                        history_lines[-1] += " " + ln
                    continue
                if role == "user":
                    user_msgs.append(content)
                history_lines.append(f"{'Пользователь' if role == 'user' else 'Ассистент'}: {content}")
            last = user_msgs[-1] if user_msgs else ""
            history = "\n".join(history_lines[:-1]) if len(history_lines) > 1 else ""
            return last, history
        return text, ""

    user_msgs = []
    history_lines = []
    for m in messages:
        if isinstance(m, dict):
            role = m.get("role", "user")
            content = m.get("content", "")
        else:
            role = "user"
            content = str(m)
        if role == "user":
            user_msgs.append(content)
        history_lines.append(f"{'Пользователь' if role == 'user' else 'Ассистент'}: {content}")
    last = user_msgs[-1] if user_msgs else ""
    history = "\n".join(history_lines[:-1]) if len(history_lines) > 1 else ""
    return last, history


def _llm_answer(question: str, sources: list, history: str = "") -> str:
    base_url = (os.getenv("LLM_BASE_URL") or os.getenv("BASE_URL") or os.getenv("OPENAI_BASE_URL", "")).rstrip("/")
    key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("LLM_MODEL") or os.getenv("GEN_MODEL") or os.getenv("OPENAI_MODEL", "qwen/qwen3.8-27b")
    if not base_url or not key:
        ctx = "\n".join(s.path + ": " + s.text[:300] for s in sources)
        return f"По базе знаний: {ctx[:500]}"
    context = "\n".join(f"{s.path} ({s.heading}): {s.text}" for s in sources)
    payload = {
        "model": model,
        "temperature": 0.0,
        "max_tokens": int(os.getenv("MAX_TOKENS", "2048")),
        "messages": [
            {"role": "system", "content": "Ты консультант МТС EnergyTool. Ответь по-русски, кратко. Не выдумывай фактов, которых нет во фрагментах. Если информации нет — скажи об этом и предложи связаться со специалистом."},
            {"role": "user", "content": (f"История:\n{history}\n\n" if history else "") + "Фрагменты базы знаний:\n" + context + "\n\nВопрос:\n" + question},
        ],
    }
    with httpx.Client(timeout=90) as client:
        r = client.post(base_url + "/chat/completions", headers={"Authorization": "Bearer " + key}, json=payload)
        r.raise_for_status()
        data = r.json()
    answer = data["choices"][0]["message"].get("content", "")
    return " ".join(answer.split()) if isinstance(answer, str) and answer.strip() else "Не могу ответить по доступным фрагментам базы знаний."


def consult(messages):
    question, history = parse_history(messages)
    chunks = get_chunks()
    sources = search(question, chunks, history=history, top_k=6)
    text = _llm_answer(question, sources, history)
    draft = {}
    return text, sources, draft


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "как снизить затраты на электроэнергию"
    text, sources, draft = consult(q)
    print("ANSWER:", text[:300])
    print("SOURCES:")
    for s in sources:
        print(" -", s.path, "|", s.heading, f"({s.score:.2f})")
