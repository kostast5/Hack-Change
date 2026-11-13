"""Общий результат consult(): его читают и судья, и веб-чат."""

from dataclasses import dataclass, field


@dataclass
class Source:
    path: str
    heading: str
    quote: str
    score: float = 0.0


@dataclass
class LeadDraft:
    """Черновик заявки. Пустой, пока клиент сам не согласился на контакт."""

    ready: bool = False
    full_name: str = ""
    phone: str = ""
    company: str = ""
    summary: str = ""


@dataclass
class ConsultResult:
    text: str
    sources: list[Source] = field(default_factory=list)
    lead: LeadDraft = field(default_factory=LeadDraft)
