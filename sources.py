"""Единый формат источника для поиска и отладки."""
import os
import sys
from pathlib import Path
from dataclasses import dataclass, asdict

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


@dataclass
class Source:
    path: str          # например "20-products/23-solar.md"
    heading: str       # заголовок раздела
    text: str          # текст чанка
    score: float = 0.0 # оценка релевантности
    quote: str = ""    # цитата для режима отладки

    def to_dict(self):
        return asdict(self)
