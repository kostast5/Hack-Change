"""Переменные окружения платформы. Значения ключей в коде не хранятся."""

import os
import sys
from pathlib import Path


def _load_local_env() -> None:
    """Подхватывает локальный .env. Уже заданные переменные не перезаписывает."""
    if os.getenv("ENERGYTOOL_SKIP_DOTENV", "").strip().lower() in {"1", "true", "yes"}:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    path = Path(__file__).resolve().parent / ".env"
    if not path.is_file():
        return
    try:
        load_dotenv(path, override=False)
    except Exception as exc:
        print(f"Не удалось прочитать .env: {type(exc).__name__}", file=sys.stderr)


_load_local_env()


def env(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    return default if not value or value == name else value


def number(name: str, default, lower, upper, kind=int):
    try:
        return max(lower, min(upper, kind(env(name))))
    except ValueError:
        return default


DATA_DIR = Path(env("DATA_DIR", "data"))
BASE_URL = (env("LLM_BASE_URL") or env("BASE_URL") or env("OPENAI_BASE_URL")).rstrip("/")
LLM_KEY = env("LLM_API_KEY") or env("OPENAI_API_KEY")
EMB_KEY = env("EMBEDDER_API_KEY") or LLM_KEY
RERANK_KEY = env("RERANKER_API_KEY") or LLM_KEY
LLM_MODEL = env("LLM_MODEL") or env("GEN_MODEL") or env("OPENAI_MODEL", "qwen/qwen3.8-27b")
EMB_MODEL = env("EMB_MODEL", "baai/bge-m3")
RERANKER_MODEL = env("RERANKER_MODEL", "qwen/qwen3-reranker-8b")
TOP_K = number("TOP_K", 4, 1, 30)
RERANKER_TOP_N = number("RERANKER_TOP_N", 2, 1, 30)
MAX_TOKENS = number("MAX_TOKENS", 2048, 128, 8192)
MAX_WORKERS = number("MAX_WORKERS", 3, 1, 8)
TEMPERATURE = number("TEMPERATURE", 0.0, 0.0, 2.0, float)
CHUNKER = env("CHUNKER", "headings")

FALLBACK = "Не могу ответить по доступным фрагментам базы знаний."
ANSWER_LIMIT = 10_000
REQUEST_TIMEOUT = 90.0
# Платформа останавливает прогон через 20 минут. Файл нужно записать раньше.
RUN_BUDGET_SEC = 18 * 60 + 30

QUESTION_NAMES = ("questions.csv", "demo_questions.csv", "train.csv")
KB_NAMES = ("knowledge-base.zip", "knowledge_base.zip", "kb.zip")


def find_file(*names: str) -> Path:
    roots: list[Path] = []
    for root in (
        DATA_DIR,
        Path.cwd() / DATA_DIR,
        Path(__file__).resolve().parent / DATA_DIR,
        Path.cwd(),
    ):
        if root not in roots:
            roots.append(root)
    for root in roots:
        for name in names:
            path = root / name
            if path.is_file():
                return path
    joined = ", ".join(names)
    raise FileNotFoundError(f"Не найдены файлы: {joined}. DATA_DIR={DATA_DIR}")


def submission_path() -> Path:
    raw = os.getenv("SUBMISSION_PATH", "").strip()
    if raw and raw != "SUBMISSION_PATH":
        return Path(raw)
    return Path("submission.csv")
