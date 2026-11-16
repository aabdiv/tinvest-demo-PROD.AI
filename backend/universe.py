"""Загрузка заранее собранной базы бумаг (data/universe.json)."""
import json
from functools import lru_cache

import numpy as np

from . import config
from .axes import AXES, SECTORS


class Universe:
    def __init__(self, data: dict):
        self.meta = {k: v for k, v in data.items() if k != "securities"}
        self.secs = data["securities"]
        self.by_id = {s["secid"]: i for i, s in enumerate(self.secs)}
        self.N = len(self.secs)
        self.S = np.array([[s["axes"][a] for a in AXES] for s in self.secs], dtype=float)  # N×5
        self.R = np.array([s["weekly_returns"] for s in self.secs], dtype=float).T  # T×N
        self.sector = np.array([s["sector"] for s in self.secs])
        self.price = np.array([s["price"] for s in self.secs], dtype=float)
        self.lot = np.array([s.get("lot") or 1 for s in self.secs], dtype=float)
        self.div = np.array([s.get("div_yield") or 0 for s in self.secs], dtype=float)
        self.weeks = data.get("weeks", [])
        # для пересчёта волатильности портфеля в балл устойчивости
        vols = np.array([s["vol"] for s in self.secs], dtype=float)
        order = np.argsort(vols)
        self.vol_sorted = vols[order]
        self.stab_sorted = self.S[order, AXES.index("stability")]
        self.cov = np.cov(self.R, rowvar=False) * 52  # годовая ковариация

    def vol_to_stability(self, vol: float) -> float:
        return float(np.interp(vol, self.vol_sorted, self.stab_sorted))

    def card(self, i: int) -> str:
        s = self.secs[i]
        tags = ", ".join(s.get("tags") or [])
        return f"{s['secid']} | {s['shortname']} | {SECTORS.get(s['sector'], s['sector'])} | {s.get('description','')} | {tags}"

    def public(self) -> list[dict]:
        keys = ["secid", "shortname", "name", "kind", "sector", "description", "tags", "price", "lot",
                "div_yield", "cagr", "vol", "axes", "maturity"]
        return [{k: s.get(k) for k in keys} for s in self.secs]


@lru_cache(maxsize=1)
def get_universe() -> Universe:
    if not config.UNIVERSE_PATH.exists():
        raise FileNotFoundError(
            f"Нет базы бумаг {config.UNIVERSE_PATH}. Запустите: python scripts/build_universe.py")
    return Universe(json.loads(config.UNIVERSE_PATH.read_text(encoding="utf-8")))
