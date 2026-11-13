"""Единый формат источника для поиска и отладки."""
from dataclasses import dataclass, asdict


@dataclass
class Source:
    path: str          # например "20-products/23-solar.md"
    heading: str       # заголовок раздела
    text: str          # текст чанка
    score: float = 0.0 # оценка релевантности
    quote: str = ""    # цитата для режима отладки

    def to_dict(self):
        return asdict(self)
