"""Вызовы OpenAI-совместимого прокси: chat, embeddings, rerank."""

import time

import httpx

from config import (
    BASE_URL,
    EMB_KEY,
    EMB_MODEL,
    LLM_KEY,
    RERANK_KEY,
    RERANKER_MODEL,
    REQUEST_TIMEOUT,
)


def make_client() -> httpx.Client:
    timeout = httpx.Timeout(REQUEST_TIMEOUT, connect=10.0)
    return httpx.Client(timeout=timeout)


def can_call(client: httpx.Client | None, key: str) -> bool:
    return client is not None and bool(BASE_URL and key)


def safe_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    for secret in (LLM_KEY, EMB_KEY, RERANK_KEY):
        if secret:
            text = text.replace(secret, "***")
    return text[:300]


def _pause(exc: BaseException) -> float:
    if isinstance(exc, httpx.HTTPStatusError):
        raw = exc.response.headers.get("Retry-After", "")
        try:
            return min(2.0, max(0.5, float(raw)))
        except ValueError:
            return 0.5
    return 0.5


def post(client: httpx.Client, endpoint: str, key: str, body: dict) -> dict:
    if not can_call(client, key):
        raise ValueError("Проверьте переменные адреса API и ключа")
    last_error: BaseException | None = None
    for attempt in range(2):
        try:
            response = client.post(
                BASE_URL + endpoint,
                headers={"Authorization": "Bearer " + key},
                json=body,
            )
            response.raise_for_status()
            try:
                return response.json()
            except ValueError as exc:
                raise ValueError("Ответ API не JSON") from exc
        except httpx.HTTPStatusError as exc:
            last_error = exc
            code = exc.response.status_code
            if code != 429 and code < 500:
                raise
            if attempt == 1:
                raise
            time.sleep(_pause(exc))
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt == 1:
                raise
            time.sleep(0.5)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Запрос к API не выполнен")


def embeddings(client: httpx.Client, texts: list[str]) -> list[list[float]]:
    result = post(client, "/embeddings", EMB_KEY, {"model": EMB_MODEL, "input": texts})
    vectors: list[list[float] | None] = [None] * len(texts)
    for index, item in enumerate(result["data"]):
        pos = int(item.get("index", index))
        raw = [float(value) for value in item["embedding"]]
        norm = sum(value * value for value in raw) ** 0.5 or 1.0
        vectors[pos] = [value / norm for value in raw]
    if any(vector is None for vector in vectors):
        raise ValueError("Не все эмбеддинги получены")
    return vectors  # type: ignore[return-value]


def rerank(client: httpx.Client, query: str, documents: list[str], top_n: int) -> list[int]:
    result = post(
        client,
        "/rerank",
        RERANK_KEY,
        {
            "model": RERANKER_MODEL,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        },
    )
    entries = result.get("results", result.get("data", []))
    return [int(item["index"]) for item in entries]
