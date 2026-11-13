"""Общий контракт консультанта: consult(messages) -> (text, sources, draft)."""
import os
import sys
from pathlib import Path

import httpx

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from consultant import parse_dialog, search_query, build_messages, clean_answer, load_prompt
from chunking import load_chunks_from_dir
from search import search


def _find_file(*names):
    """Ищет файл так же, как solution.py: DATA_DIR, parent/DATA_DIR, cwd."""
    data_dir = os.getenv("DATA_DIR", "data")
    roots = (Path(data_dir), Path(__file__).resolve().parent / data_dir, Path.cwd())
    for root in roots:
        for name in names:
            path = root / name
            if path.is_file():
                return path
    return None


_CHUNKS = None


def get_chunks():
    global _CHUNKS
    if _CHUNKS is None:
        kb = _find_file("knowledge-base.zip", "knowledge_base.zip", "kb.zip")
        if kb is not None:
            import tempfile, zipfile
            tmp = Path(tempfile.mkdtemp())
            with zipfile.ZipFile(kb) as z:
                z.extractall(tmp)
            root = tmp
        else:
            data_dir = os.getenv("DATA_DIR", "data")
            root = Path(data_dir)
            if not root.is_dir():
                root = Path(__file__).resolve().parent / data_dir
        _CHUNKS = load_chunks_from_dir(str(root))
    return _CHUNKS


def _llm_answer(llm_messages: list) -> str:
    base_url = (os.getenv("LLM_BASE_URL") or os.getenv("BASE_URL") or os.getenv("OPENAI_BASE_URL", "")).rstrip("/")
    key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("LLM_MODEL") or os.getenv("GEN_MODEL") or os.getenv("OPENAI_MODEL", "qwen/qwen3.8-27b")
    if not base_url or not key:
        # fallback без LLM: собрать контекст
        last = llm_messages[-1]["content"] if llm_messages else ""
        return "Не могу ответить по доступным фрагментам базы знаний."
    payload = {
        "model": model,
        "temperature": float(os.getenv("TEMPERATURE", "0.0")),
        "max_tokens": int(os.getenv("MAX_TOKENS", "2048")),
        "messages": llm_messages,
    }
    with httpx.Client(timeout=90) as client:
        r = client.post(base_url + "/chat/completions", headers={"Authorization": "Bearer " + key}, json=payload)
        r.raise_for_status()
        data = r.json()
    raw = data["choices"][0]["message"].get("content", "")
    return clean_answer(raw)


def consult(messages):
    """Возвращает (text, list[Source], draft_dict)."""
    if isinstance(messages, str):
        msgs = parse_dialog(messages)
    else:
        msgs = messages if isinstance(messages, list) else parse_dialog(str(messages))

    q = search_query(msgs)
    chunks = get_chunks()
    sources = search(q, chunks, history="", top_k=6)
    context = "\n".join(f"{s.path} ({s.heading}): {s.text}" for s in sources)
    llm_messages = build_messages(msgs, context)
    text = _llm_answer(llm_messages)
    if not text or not text.strip():
        text = "Не могу ответить по доступным фрагментам базы знаний."
    draft = {}
    return text, sources, draft


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "как снизить затраты на электроэнергию"
    text, sources, draft = consult(q)
    print("ANSWER:", text[:500])
    print("SOURCES:")
    for s in sources:
        print(" -", s.path, "|", s.heading, f"({s.score:.2f})")
