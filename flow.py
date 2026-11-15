"""Заявка, кнопки ответа, слабый поиск и кэш. В CSV судьи это не пишется."""

import json
import re
import threading
from pathlib import Path

from config import LLM_MODEL
from contract import LeadDraft, Source
from retrieve import rank_chunks, tokenize

# Ниже этого лексического балла фрагмент есть, но отвечать по нему рано.
# 18 демо-вопросов держатся от 6.25, поэтому порог их не задевает.
WEAK_SCORE = 5.0
CACHE_LIMIT = 200
_CACHE_PATH = Path(__file__).resolve().parent / "out" / "answer-cache.json"
_cache_lock = threading.Lock()
_cache: dict[str, dict] | None = None

CLARIFY = (
    "Подскажите, с чем могу вам помочь?"
)
TASK_BUTTONS = ["Счета и тарифы", "Сбор показаний", "Потери в сети", "Солнечная станция"]
POWER_BAND_BUTTONS = ["Меньше 750 кВт", "750 кВт – 20 МВт", "Больше 20 МВт"]
_POWER_BAND = re.compile(
    r"меньше\s*750|менее\s*750|"
    r"750\s*квт\s*[–\-]\s*20|"
    r"больше\s*20\s*мвт|"
    r"\d+[\s,.]?\d*\s*мвт|"
    r"\d+[\s,.]?\d*\s*квт",
    re.I,
)
_NUM_UNIT = re.compile(
    r"(\d[\d\s,.]*)\s*(мвт|mw|квт\s*·?\s*ч|квтч|квт|kw)\b",
    re.I,
)

# Приветствие с кнопки «Другой вопрос» — только интерфейс, не ответ модели.
UI_GREETING = "Здравствуйте! Чем могу вам помочь?"

_REFUSAL = re.compile(
    r"не\s+готов\w*(?:\s+\w+){0,4}\s+(?:оставлять|оставить|дать|давать|сообщать)|"
    r"не\s+хочу\s+(?:оставлять|оставить|давать|сообщать)|"
    r"без\s+телефон|не\s+звоните|телефон\s+не\s+дам",
    re.I,
)
_CONSENT = re.compile(
    r"оставить\s+заявк|оставлю\s+заявк|готов[аы]?\s+оставить|"
    r"хочу\s+заявк|оформ\w*\s+заявк|свяжит\w*|перезвон\w*|позвоните|"
    r"мой\s+телефон|номер\s+телефон|пусть\s+специалист|жду\s+звонк|"
    r"оставлю\s+контакт|можно\s+со\s+мной\s+связат",
    re.I,
)
_PHONE = re.compile(r"(?:\+7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")
_COMPANY = re.compile(
    r"(?:ООО|АО|ПАО|ЗАО|ОАО|ИП)\s+[«\"']?[0-9A-Za-zА-Яа-яЁё][\w\s\-]{1,50}",
    re.I,
)
_COMPANY_WORD = re.compile(
    r"компани[яи]\s+[«\"]([0-9A-Za-zА-Яа-яЁё][^»\"\n]{1,50})",
    re.I,
)
_NAME = re.compile(
    r"(?:меня зовут|мое имя)\s+([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){0,2})",
    re.I,
)


def strip_ui_greeting(messages: list[dict]) -> list[dict]:
    """Убирает статическое приветствие чата перед consult и кэшем."""
    return [
        message
        for message in messages
        if not (
            message.get("role") == "assistant"
            and _flat(message.get("content", "")) == _flat(UI_GREETING)
        )
    ]


def retrieval_is_weak(question: str, facts: str, chunks) -> bool:
    """Фрагменты нашлись, но оценка слишком слабая, чтобы отвечать по ним."""
    ranked = rank_chunks(question, facts, chunks)
    if not ranked:
        return False
    score = ranked[0][0]
    if facts.strip():
        return score < 3.0
    return score < WEAK_SCORE


def _normalize_number(raw: str) -> str:
    return raw.replace(" ", "").replace(",", ".").strip()


def _consumption_line_from_dialog(messages: list[dict]) -> str:
    """Ответ на вопрос про месячный расход (кВт·ч), в т.ч. с единицами и опечатками."""
    for index, msg in enumerate(messages):
        if msg.get("role") != "assistant":
            continue
        text = (msg.get("content") or "").lower().replace("ё", "е")
        if not re.search(r"квт\s*·?\s*ч|квтч", text) and not (
            "расход" in text and re.search(r"месяц|мес", text)
        ):
            continue
        for nxt in messages[index + 1 :]:
            if nxt.get("role") != "user":
                continue
            raw = (nxt.get("content") or "").strip()
            if re.fullmatch(r"\d[\d\s]{0,9}", raw):
                return f"месячный расход — {_normalize_number(raw)} кВт·ч (уже ответил)"
            match = _NUM_UNIT.search(raw)
            if match:
                value = _normalize_number(match.group(1))
                unit = match.group(2).lower().replace(" ", "")
                if "мвт" in unit or unit == "mw":
                    return (
                        f"на вопрос про кВт·ч клиент написал {value} МВт — это мощность, не расход; "
                        f"зафиксируй {value} МВт и не переспрашивай про месячный объём в кВт·ч"
                    )
                if "квтч" in unit or "квт·ч" in match.group(2).lower():
                    return f"месячный расход — {value} кВт·ч (уже ответил)"
                if unit.startswith("квт") or unit == "kw":
                    return f"клиент указал {value} кВт (уточни при необходимости, но не повторяй тот же вопрос)"
            elif raw:
                return f"на вопрос про расход клиент ответил: «{raw[:80]}» (не переспрашивай дословно)"
            break
    return ""


def _monthly_kwh_from_dialog(messages: list[dict]) -> str:
    line = _consumption_line_from_dialog(messages)
    if not line:
        return ""
    if line.startswith("месячный расход"):
        match = re.search(r"(\d[\d.]+)", line)
        return match.group(1) if match else "1"
    return "1"


def _bill_from_dialog(messages: list[dict]) -> str:
    for index, msg in enumerate(messages):
        if msg.get("role") != "assistant":
            continue
        text = (msg.get("content") or "").lower().replace("ё", "е")
        if not re.search(r"счет|счёт|сумм", text):
            continue
        for nxt in messages[index + 1 :]:
            if nxt.get("role") != "user":
                continue
            raw = _normalize_number((nxt.get("content") or "").strip())
            if re.fullmatch(r"\d+", raw):
                return f"сумма в счёте — {raw} ₽"
            break
    return ""


def _power_from_user_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    blob = raw.lower().replace("ё", "е")
    for label in POWER_BAND_BUTTONS:
        if label.lower().replace("ё", "е") in blob:
            return f"присоединённая мощность — {label}"
    if re.search(r"меньше\s*750|менее\s*750", blob):
        return "присоединённая мощность — меньше 750 кВт"
    if re.search(r"750\s*квт", blob) and re.search(r"20\s*мвт", blob):
        return "присоединённая мощность — 750 кВт – 20 МВт"
    if re.search(r"больше\s*20", blob):
        return "присоединённая мощность — больше 20 МВт"
    if re.fullmatch(r"\d+", _normalize_number(blob)):
        return ""
    match = _NUM_UNIT.search(blob)
    if not match:
        return ""
    unit = match.group(2).lower()
    value = _normalize_number(match.group(1))
    if "мвт" in unit or unit == "mw":
        return f"присоединённая мощность — {value} МВт (уже указал)"
    if unit.startswith("квт") and "ч" not in unit:
        try:
            kw = float(value)
        except ValueError:
            return ""
        if kw < 750:
            return "присоединённая мощность — меньше 750 кВт"
        if kw <= 20_000:
            return "присоединённая мощность — 750 кВт – 20 МВт"
    return ""


def _power_line_from_messages(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        line = _power_from_user_text(str(msg.get("content", "")))
        if line:
            return line
    return ""


def _price_category_from_dialog(blob: str) -> str:
    for pattern in (
        r"(?:ценов\w*\s*)?категор\w*\s*(?:№\s*)?([1-6])",
        r"\b([1-6])\s*[-–]?\s*(?:я\s*)?ценов",
        r"\b(первая|вторая|третья|четверт|пят|шест)\w*\s+ценов",
    ):
        match = re.search(pattern, blob, re.I)
        if match:
            return match.group(0).strip()
    return ""


def dialog_memory(messages: list[dict]) -> str:
    """Краткая память диалога для промпта: не переспрашивать известное."""
    users = [m["content"] for m in messages if m.get("role") == "user" and m.get("content")]
    blob = " ".join(users).lower().replace("ё", "е")
    parts: list[str] = []

    power = _power_line_from_messages(messages)
    if power:
        parts.append(power)

    consumption = _consumption_line_from_dialog(messages)
    if consumption:
        parts.append(consumption)

    bill = _bill_from_dialog(messages)
    if bill:
        parts.append(bill)

    category = _price_category_from_dialog(blob)
    if category:
        parts.append(f"ценовая категория — {category}")

    if not parts:
        return ""
    return (
        "Уже известно от клиента (не переспрашивай то же самое; если факт уже есть — следующий шаг или вывод, "
        "без повторного вопроса дословно):\n"
        + "\n".join(f"— {item}" for item in parts)
    )


def user_already_named_power(messages: list[dict] | None) -> bool:
    """Клиент уже выбрал или написал диапазон мощности — кнопки не повторяем."""
    if not messages:
        return False
    blob = " ".join(
        str(message.get("content", ""))
        for message in messages
        if message.get("role") == "user" and message.get("content")
    ).lower().replace("ё", "е")
    for label in POWER_BAND_BUTTONS:
        if label.lower().replace("ё", "е") in blob:
            return True
    return bool(_POWER_BAND.search(blob))


def _flat(text: str) -> str:
    return " ".join((text or "").split())


def client_is_ready(text: str) -> bool:
    """Клиент сам согласен на контакт. Отказ от телефона важнее согласия."""
    flat = (text or "").lower().replace("ё", "е")
    if not flat.strip():
        return False
    if _REFUSAL.search(flat):
        return False
    return bool(_PHONE.search(flat) or _CONSENT.search(flat))


def _clip(text: str, limit: int) -> str:
    flat = _flat(text)
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


def _product(sources: list[Source]) -> str:
    blob = " ".join(source.path for source in sources[:4]).lower()
    pairs = (
        ("23-solar", "солнечная станция"),
        ("22-askue", "платформа учёта (АСКУЭ)"),
        ("25-meter", "распознавание показаний по фото"),
        ("24-losses", "поиск потерь"),
        ("21-orem", "выход на оптовый рынок"),
        ("14-tariffs", "разбор счетов и тарифа"),
        ("12-power", "порог присоединённой мощности"),
    )
    for key, name in pairs:
        if key in blob:
            return name
    if sources:
        return "консультация Energytool по электроэнергии"
    return "продукт пока не выбран"


def _gaps(product: str, dialogue: str) -> str:
    text = dialogue.lower().replace("ё", "е")
    missing: list[str] = []
    if "солнеч" in product:
        if not re.search(r"регион|москв|област|город|краснодар|петербург", text):
            missing.append("регион")
        if not re.search(r"кровл|крыш|шифер|фасад", text):
            missing.append("тип и возраст кровли")
        if not re.search(r"днем|вечер|круглосут", text):
            missing.append("когда объект потребляет больше")
        if not re.search(r"отключ|резерв|накопител", text):
            missing.append("нужен ли резерв при отключениях")
    elif "учёт" in product or "аскуэ" in product or "фото" in product:
        if not re.search(r"\d+", text):
            missing.append("сколько приборов")
        if not re.search(r"вручн|автомат|фото|техник", text):
            missing.append("как сейчас снимают показания")
        if not re.search(r"аренд|цех|объект|магазин|склад", text):
            missing.append("нужен ли учёт по объектам")
    elif "оптовый" in product or "мощност" in product:
        if not re.search(r"квт|мвт|\d+", text):
            missing.append("присоединённая мощность")
        if not re.search(r"категор", text):
            missing.append("ценовая категория")
    elif "потер" in product:
        if not re.search(r"почасов|сутк|интервал", text):
            missing.append("какие данные учёта есть")
        if not re.search(r"год|месяц|период", text):
            missing.append("за какой период")
    elif "счет" in product or "тариф" in product:
        if not re.search(r"категор", text):
            missing.append("ценовая категория")
        if not re.search(r"квт", text):
            missing.append("объём потребления")
    else:
        missing.append("объект и что нужно получить от специалиста")
    return ", ".join(missing) if missing else "адрес объекта и вводные для расчёта"


def build_lead(messages: list[dict], sources: list[Source]) -> LeadDraft:
    """Резюме для менеджера из реплик клиента. Факты не дописываются."""
    users = [message["content"] for message in messages if message.get("role") == "user" and message.get("content")]
    dialogue = " ".join(users)
    flat = dialogue.replace("ё", "е")
    phone_match = _PHONE.search(flat)
    org_match = _COMPANY.search(dialogue)
    word_match = _COMPANY_WORD.search(dialogue)
    name_match = _NAME.search(flat)
    if org_match:
        company = _clip(org_match.group(0), 80)
    elif word_match:
        company = _clip(word_match.group(1), 80)
    else:
        company = ""
    task = _clip(users[0], 220) if users else "вопрос не сформулирован"
    who_company = company or "компания не названа"
    who_name = _clip(name_match.group(1), 80) if name_match else "имя не указано"
    product = _product(sources)
    later = [text for text in users[1:] if text and not client_is_ready(text)]
    parts = [
        f"Клиент: {who_name}, {who_company}.",
        f"Начал так: «{task}».",
    ]
    if later:
        parts.append(f"Дальше рассказал: {_clip(' '.join(later), 240)}.")
    parts.append(f"По разговору ближе всего {product}.")
    parts.append(f"На звонке уточнить: {_gaps(product, dialogue)}.")
    summary = " ".join(parts)
    return LeadDraft(
        ready=True,
        full_name=_clip(name_match.group(1), 80) if name_match else "",
        phone=_clip(phone_match.group(0), 24) if phone_match else "",
        company=company,
        summary=summary,
    )


def cache_key(messages: list[dict]) -> str:
    body = [{"role": message["role"], "content": message["content"]} for message in messages]
    return "talk20\n" + LLM_MODEL + "\n" + json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def _load_cache() -> dict[str, dict]:
    global _cache
    if _cache is not None:
        return _cache
    _cache = {}
    if not _CACHE_PATH.is_file():
        return _cache
    try:
        raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _cache
    if isinstance(raw, dict):
        _cache = {str(key): value for key, value in raw.items() if isinstance(value, dict)}
    return _cache


def _store_cache() -> None:
    if _cache is None:
        return
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = _CACHE_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
        temporary.replace(_CACHE_PATH)
    except OSError:
        return


def cache_get(key: str) -> dict | None:
    with _cache_lock:
        found = _load_cache().get(key)
        return dict(found) if found else None


def cache_put(key: str, payload: dict) -> None:
    with _cache_lock:
        store = _load_cache()
        store[key] = payload
        if len(store) > CACHE_LIMIT:
            for old in list(store)[: len(store) - CACHE_LIMIT]:
                store.pop(old, None)
        _store_cache()


def cache_clear() -> None:
    """Сброс файлового и процессного кэша ответов (локальная отладка чата)."""
    global _cache
    with _cache_lock:
        _cache = {}
        try:
            if _CACHE_PATH.is_file():
                _CACHE_PATH.unlink()
        except OSError:
            pass


def sources_from_cache(raw) -> list[Source]:
    sources = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        sources.append(
            Source(
                path=str(item.get("path", "")),
                heading=str(item.get("heading", "")),
                quote=str(item.get("quote", "")),
                score=float(item.get("score") or 0),
            )
        )
    return sources


def lead_from_cache(raw) -> LeadDraft:
    if not isinstance(raw, dict) or not raw.get("ready"):
        return LeadDraft()
    return LeadDraft(
        ready=True,
        full_name=str(raw.get("full_name", "")),
        phone=str(raw.get("phone", "")),
        company=str(raw.get("company", "")),
        summary=str(raw.get("summary", "")),
    )
