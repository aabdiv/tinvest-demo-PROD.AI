"""Подбор бумаг и долей без LLM: фильтр по красным линиям → кандидаты → оптимизация формы портфеля.

Цель: фигура портфеля (взвешенная сумма фигур бумаг) как можно ближе к целевой с учётом весов осей.
Устойчивость портфеля считается не средней по бумагам, а из реальной волатильности портфеля
(ковариация недельных доходностей), то есть с учётом диверсификации.
"""
import math

import numpy as np
from scipy.optimize import minimize

from .axes import AXES, AXIS_RU, SECTORS
from .profile import Profile
from .universe import Universe

STAB = AXES.index("stability")


def fit_score(vec: np.ndarray, target: np.ndarray, w: np.ndarray) -> float:
    return float(max(0.0, 100 - 10 * (np.abs(vec - target) * w).sum() / w.sum()))


def constraints_from(U: Universe, prof: Profile):
    allowed = np.ones(U.N, dtype=bool)
    max_pos, sector_caps, dd_limit = 0.25, {}, None
    for rl in prof.red_lines:
        if rl.kind == "exclude_sector" and rl.sector:
            allowed &= U.sector != rl.sector
        elif rl.kind == "exclude_security" and rl.secid in U.by_id:
            allowed[U.by_id[rl.secid]] = False
        elif rl.kind == "max_position" and rl.value:
            max_pos = min(max_pos, float(rl.value))
        elif rl.kind == "max_sector_share" and rl.sector and rl.value is not None:
            sector_caps[rl.sector] = min(sector_caps.get(rl.sector, 1.0), float(rl.value))
        elif rl.kind == "max_drawdown_rub" and rl.value:
            dd_limit = float(rl.value) if dd_limit is None else min(dd_limit, float(rl.value))
    return allowed, max(max_pos, 0.02), sector_caps, dd_limit


def theme_relevance(U: Universe, prof: Profile):
    rel = np.zeros(U.N)
    groups = []
    for th in prof.themes:
        idx, r = [], []
        for m in th.matches:
            i = U.by_id.get(m.get("secid"))
            if i is not None:
                idx.append(i)
                r.append(float(m.get("relevance", 0.5)))
                rel[i] = max(rel[i], float(m.get("relevance", 0.5)))
        if idx:
            groups.append({"theme": th, "idx": idx, "rel": r, "cap": float(th.max_share)})
    return rel, groups


def portfolio_axes(U: Universe, idx: list[int], x: np.ndarray) -> np.ndarray:
    vec = x @ U.S[idx]
    sub = U.cov[np.ix_(idx, idx)]
    vol = math.sqrt(max(float(x @ sub @ x), 0.0))
    vec[STAB] = U.vol_to_stability(vol)
    return vec


def backtest(U: Universe, idx: list[int], x: np.ndarray, amount: float) -> dict:
    r = U.R[:, idx] @ x
    values = amount * np.cumprod(1 + r)
    years = len(r) / 52
    ann = (values[-1] / amount) ** (1 / years) - 1 if years > 0 else 0.0
    peak = np.maximum.accumulate(np.concatenate([[amount], values]))[1:]
    dd = float((values / peak - 1).min())
    return {
        "ann_return": float(ann), "ann_vol": float(r.std() * math.sqrt(52)),
        "max_dd_pct": -dd, "max_dd_rub": -dd * amount, "values": values,
    }


def _clean(x: np.ndarray, cap: float) -> np.ndarray:
    x = np.where(x < 0.01, 0, x)
    x = x / x.sum()
    for _ in range(10):
        over = x > cap + 1e-9
        if not over.any():
            break
        excess = (x[over] - cap).sum()
        x[over] = cap
        free = (~over) & (x > 0) & (x < cap)
        if not free.any():
            break
        x[free] += excess * x[free] / x[free].sum()
    return x


def _solve(U, idx, T, W, max_pos, sector_caps, groups, gamma):
    n = len(idx)
    S = U.S[idx]
    sub_cov = U.cov[np.ix_(idx, idx)]
    pos = {i: k for k, i in enumerate(idx)}
    gsets = [(np.array([pos[i] for i in g["idx"] if i in pos]), g["cap"]) for g in groups]
    gsets = [(a, c) for a, c in gsets if len(a)]
    sec_sets = []
    for sec, cap in sector_caps.items():
        members = np.array([k for k, i in enumerate(idx) if U.sector[i] == sec])
        if len(members):
            sec_sets.append((members, cap))

    def obj(x):
        vec = x @ S
        var = float(x @ sub_cov @ x)
        vec[STAB] = U.vol_to_stability(math.sqrt(max(var, 0)))
        f = float(((vec - T) ** 2 * W).sum() / W.sum())
        f += gamma * var * 10 + 0.5 * float((x ** 2).sum())
        for members, cap in gsets:
            short = cap - x[members].sum()
            if short > 0:
                f += 40 * short ** 2
        return f

    cons = [{"type": "eq", "fun": lambda x: x.sum() - 1}]
    for members, cap in gsets + sec_sets:
        cons.append({"type": "ineq", "fun": lambda x, m=members, c=cap: c - x[m].sum()})
    x0 = np.full(n, 1.0 / n)
    res = minimize(obj, x0, method="SLSQP", bounds=[(0, max_pos)] * n, constraints=cons,
                   options={"maxiter": 300, "ftol": 1e-7})
    x = np.clip(res.x, 0, None)
    return _clean(x, max_pos) if x.sum() > 0 else x0


def optimize(U: Universe, prof: Profile) -> dict:
    T = np.array([prof.target[a] for a in AXES])
    W = np.array([prof.importance[a] for a in AXES])
    allowed, max_pos, sector_caps, dd_limit = constraints_from(U, prof)
    rel, groups = theme_relevance(U, prof)
    notes = []

    dist = np.sqrt((((U.S - T) ** 2) * W).sum(1) / W.sum())
    score = -dist + 2.0 * rel
    order = [i for i in np.argsort(-score) if allowed[i]]
    k = max(30, math.ceil(1 / max_pos) + 5)
    idx = list(order[:k])
    for g in groups:  # лучшие бумаги каждой темы попадают в кандидаты
        best = sorted([i for i in g["idx"] if allowed[i]], key=lambda i: -rel[i])[:6]
        idx += [i for i in best if i not in idx]
    if len(idx) * max_pos < 1:
        return {"error": "Слишком жёсткие красные линии: не из чего собрать портфель."}

    chosen, bt, gamma = None, None, 0.0
    for gamma in [0.0, 2, 6, 15, 40, 100]:
        x = _solve(U, idx, T, W, max_pos, sector_caps, groups, gamma)
        bt = backtest(U, idx, x, prof.amount)
        chosen = x
        if dd_limit is None or bt["max_dd_rub"] <= dd_limit:
            break
    dd_ok = dd_limit is None or bt["max_dd_rub"] <= dd_limit
    if not dd_ok:
        notes.append(f"Даже самый осторожный набор из доступных бумаг за 3 года проседал до "
                     f"−{bt['max_dd_rub'] / 1000:.0f} тыс. ₽ — больше вашей красной линии.")

    achieved = portfolio_axes(U, idx, chosen)
    for k_, a in enumerate(AXES):
        if W[k_] >= 2 and abs(achieved[k_] - T[k_]) >= 1.5:
            notes.append(f"«{AXIS_RU[a]}»: хотели {T[k_]:.1f}, из доступных бумаг получилось {achieved[k_]:.1f}.")

    holdings = []
    for j, i in enumerate(idx):
        if chosen[j] <= 0:
            continue
        holdings.append(security_row(U, i, T, W, prof.amount, chosen[j], rel[i], groups))
    holdings.sort(key=lambda h: -h["weight"])
    held = {h["secid"] for h in holdings}
    near = [security_row(U, i, T, W, prof.amount, 0.0, rel[i], groups) for i in order if U.secs[i]["secid"] not in held][:12]
    blocked_idx = [i for i in np.argsort(dist) if not allowed[i]][:6]
    blocked = [security_row(U, i, T, W, prof.amount, 0.0, rel[i], groups, blocked=_why_blocked(U, i, prof)) for i in blocked_idx]

    sectors = {}
    for h in holdings:
        sectors[h["sector"]] = sectors.get(h["sector"], 0) + h["weight"]
    step = max(1, len(bt["values"]) // 160)
    return {
        "target": dict(zip(AXES, T.round(2).tolist())),
        "importance": dict(zip(AXES, W.round(2).tolist())),
        "achieved": dict(zip(AXES, achieved.round(2).tolist())),
        "fit": round(fit_score(achieved, T, W)),
        "holdings": holdings,
        "candidates": near,
        "blocked": blocked,
        "sectors": sorted([{"sector": s, "name": SECTORS.get(s, s), "weight": round(w, 4)} for s, w in sectors.items()],
                          key=lambda d: -d["weight"]),
        "metrics": {
            "ann_return": round(bt["ann_return"], 4), "ann_vol": round(bt["ann_vol"], 4),
            "max_dd_pct": round(bt["max_dd_pct"], 4), "max_dd_rub": round(bt["max_dd_rub"]),
            "income_year_rub": round(prof.amount * float(sum(h["weight"] * (h["div_yield"] or 0) for h in holdings))),
            "n": len(holdings), "dd_limit_rub": dd_limit, "dd_ok": dd_ok,
        },
        "backtest": {"dates": U.weeks[::step], "values": [round(v) for v in bt["values"][::step]]},
        "notes": notes,
    }


def _why_blocked(U: Universe, i: int, prof: Profile) -> str:
    s = U.secs[i]
    for rl in prof.red_lines:
        if rl.kind == "exclude_sector" and rl.sector == s["sector"]:
            return rl.label
        if rl.kind == "exclude_security" and rl.secid == s["secid"]:
            return rl.label
    return "красная линия"


def security_row(U, i, T, W, amount, weight, rel, groups, blocked=None) -> dict:
    s = U.secs[i]
    vec = U.S[i]
    gaps = np.abs(vec - T) * W
    g = int(np.argmax(gaps))
    rub = amount * weight
    lots = int(rub // (s["price"] * (s.get("lot") or 1))) if weight > 0 and s["price"] else 0
    theme = next((g_["theme"].query for g_ in groups if i in g_["idx"]), None)
    return {
        "secid": s["secid"], "shortname": s["shortname"], "name": s["name"], "kind": s["kind"],
        "sector": s["sector"], "sector_ru": SECTORS.get(s["sector"], s["sector"]),
        "description": s.get("description", ""), "axes": s["axes"], "weight": round(float(weight), 4),
        "rub": round(rub), "lots": lots, "price": s["price"], "lot": s.get("lot") or 1,
        "div_yield": s.get("div_yield") or 0, "fit": round(fit_score(vec, T, W)),
        "gap_axis": AXES[g], "theme": theme, "theme_rel": round(float(rel), 2), "blocked": blocked,
    }
