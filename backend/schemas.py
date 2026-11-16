"""Состояние профиля — единственный источник правды.

Фронтенд хранит состояние у себя и присылает его в каждом запросе, бэкенд возвращает обновлённое.
Текст, правки паутины и красные линии только меняют состояние; поиск и мандат только читают его.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

RedLineKind = Literal["exclude_sector", "exclude_security", "max_position", "max_sector_share",
                      "max_drawdown_rub", "no_margin"]


class RedLine(BaseModel):
    id: str
    kind: RedLineKind
    sector: Optional[str] = None
    secid: Optional[str] = None
    value: Optional[float] = None
    label: str
    source: str = "вручную"
    active: bool = True


class Theme(BaseModel):
    id: str
    query: str
    max_share: float = 0.1
    source: str = "вручную"
    active: bool = True
    resolved: bool = False
    matches: list[dict] = Field(default_factory=list)  # [{secid, relevance, why}]


class Wish(BaseModel):
    id: str
    span: str
    label: str
    type: Literal["axis", "red_line", "theme", "param", "fear", "other"]
    effects: dict[str, float] = Field(default_factory=dict)
    red_line: Optional[RedLine] = None
    theme: Optional[Theme] = None
    horizon_years: Optional[int] = None
    amount_rub: Optional[float] = None
    confidence: float = 0.8
    status: Literal["accepted", "rejected"] = "accepted"


class Conflict(BaseModel):
    id: str
    text: str
    options: list[str]
    resolved: bool = False


class Holding(BaseModel):
    secid: str
    weight: float


class State(BaseModel):
    messages: list[str] = Field(default_factory=list)
    wishes: list[Wish] = Field(default_factory=list)
    manual_axes: dict[str, float] = Field(default_factory=dict)  # закреплённые руками оси
    manual_red_lines: list[RedLine] = Field(default_factory=list)
    disabled_defaults: list[str] = Field(default_factory=list)
    manual_themes: list[Theme] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    amount_rub: float = 500_000
    horizon_years: int = 5
    autonomy: Literal["ask", "auto"] = "ask"
    executed: Optional[list[Holding]] = None  # что агент реально «купил»
    executed_value: Optional[float] = None
    sim_step: int = 0
    agent_log: list[dict] = Field(default_factory=list)
    seq: int = 0  # счётчик для id


class Req(BaseModel):
    state: State
    text: Optional[str] = None
    secid: Optional[str] = None
    conflict_id: Optional[str] = None
    after: Optional[list[Holding]] = None
