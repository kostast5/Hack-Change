"""Единый формат источника для поиска и отладки."""
from dataclasses import dataclass, asdict


@dataclass
class Source:
    path: str
    heading: str    
    text: str  
    score: float = 0.0
    quote: str = "" 

    def to_dict(self):
        return asdict(self)
