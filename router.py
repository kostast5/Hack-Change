"""Роутер по карте продуктов: задача клиента -> файл(ы) продукта."""
import re

ROUTES = [
    {
        "name": "Выход на оптовый рынок",
        "files": ["20-products/21-orem.md"],
        "keywords": [
            "оптовый", "оптов", "закупк", "крупн", "предприят", "снизить затрат",
            "750 квт", "мощност", "ценов категор", "присоедин",
        ],
    },
    {
        "name": "Облачная платформа учёта",
        "files": ["20-products/22-askue.md"],
        "keywords": [
            "учёт", "учет", "показан", "объект", "анализ", "потреблен", "аскуэ",
            "облачн", "сбор показан", "мониторинг",
        ],
    },
    {
        "name": "Распознавание показаний по фото",
        "files": ["20-products/25-meter-reading.md"],
        "keywords": [
            "фото", "фотограф", "показан", "прибор", "счётчик", "счетчик",
            "распознав", "ocr", "не подключ",
        ],
    },
    {
        "name": "Поиск коммерческих потерь",
        "files": ["20-products/24-losses.md"],
        "keywords": [
            "потер", "хищен", "незаконн", "коммерческ", "сет", "вмешательств",
            "неплательщик",
        ],
    },
    {
        "name": "Сетевая солнечная станция",
        "files": ["20-products/23-solar.md"],
        "keywords": [
            "солнеч", "станци", "генерац", "свой генерац", "снизить закупк",
            "днём", "днем", "крыша", "панел",
        ],
    },
    {
        "name": "Гибридная солнечная станция с накопителями",
        "files": ["20-products/23-solar.md"],
        "keywords": [
            "гибрид", "накопител", "аккумулятор", "резерв", "перебо", "отключен",
            "надёжност", "надежност", "бесперебойн",
        ],
    },
]

COMMON_FILES = [
    "00-reference/00-product-map.md",
    "00-reference/02-product-scope-and-limits.md",
    "20-products/20-portfolio.md",
    "20-products/26-general.md",
]


def _norm(text: str) -> str:
    return text.lower().replace("ё", "е")


def route(question: str, history: str = "") -> list[str]:
    q = _norm(question + " " + history)
    chosen: set[str] = set()
    for r in ROUTES:
        if any(kw in q for kw in r["keywords"]):
            chosen.update(r["files"])
    if not chosen:
        chosen.update(f["files"][0] for f in ROUTES if f["files"])
    # Добавляем общие файлы.
    chosen.update(COMMON_FILES)
    return sorted(chosen)


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "солнечная станция на крыше"
    print(route(q))
