"""Свёртка состояния в профиль: целевая фигура, веса осей, красные линии, темы."""
from dataclasses import dataclass, field

from .axes import AXES, NEUTRAL
from .schemas import RedLine, State, Theme

DEFAULT_LINES = [
    RedLine(id="def_maxpos", kind="max_position", value=0.12, label="Не больше 12% в одной бумаге", source="по умолчанию"),
    RedLine(id="def_nomargin", kind="no_margin", label="Без заёмных денег", source="по умолчанию"),
]


@dataclass
class Profile:
    target: dict
    importance: dict
    pinned: list
    red_lines: list = field(default_factory=list)
    themes: list = field(default_factory=list)
    amount: float = 500_000
    horizon: int = 5


def clamp(v: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, v))


def all_red_lines(state: State) -> list[RedLine]:
    lines = [l for l in DEFAULT_LINES if l.id not in state.disabled_defaults]
    for w in state.wishes:
        if w.status == "accepted" and w.red_line:
            lines.append(w.red_line)
    lines += state.manual_red_lines
    return lines


def all_themes(state: State) -> list[Theme]:
    out = [w.theme for w in state.wishes if w.status == "accepted" and w.theme]
    return out + list(state.manual_themes)


def fold(state: State) -> Profile:
    sums = {a: 0.0 for a in AXES}
    for w in state.wishes:
        if w.status != "accepted":
            continue
        for a, v in w.effects.items():
            if a in sums:
                sums[a] += v
    target = {a: clamp(NEUTRAL + sums[a]) for a in AXES}
    importance = {a: 1.0 + min(2.0, abs(sums[a]) / 1.5) for a in AXES}
    # короткий горизонт делает устойчивость важнее
    if state.horizon_years <= 2:
        importance["stability"] += 1.0
    for a, v in state.manual_axes.items():
        if a in target:
            target[a] = clamp(float(v))
            importance[a] = max(importance[a], 2.5)
    return Profile(
        target={a: round(v, 2) for a, v in target.items()},
        importance=importance,
        pinned=list(state.manual_axes.keys()),
        red_lines=[l for l in all_red_lines(state) if l.active],
        themes=[t for t in all_themes(state) if t.active],
        amount=state.amount_rub,
        horizon=state.horizon_years,
    )
