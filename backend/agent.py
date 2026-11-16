"""Агент: исполнение портфеля, симуляция месяца на реальных доходностях и предложение сделок."""
import numpy as np

from .axes import AXES
from .optimizer import backtest, fit_score, portfolio_axes
from .profile import Profile
from .universe import Universe


def _vec(U: Universe, weights: dict) -> tuple[list[int], np.ndarray, np.ndarray]:
    idx = [U.by_id[s] for s in weights if s in U.by_id]
    x = np.array([weights[U.secs[i]["secid"]] for i in idx], dtype=float)
    x = x / x.sum() if x.sum() > 0 else x
    return idx, x, portfolio_axes(U, idx, x)


def check_red_lines(U: Universe, prof: Profile, weights: dict, amount: float) -> list[dict]:
    out = []
    idx, x, _ = _vec(U, weights)
    w = {U.secs[i]["secid"]: float(x[k]) for k, i in enumerate(idx)}
    for rl in prof.red_lines:
        ok = True
        if rl.kind == "max_position" and rl.value:
            ok = max(w.values(), default=0) <= rl.value + 0.005
        elif rl.kind == "exclude_sector":
            ok = all(U.secs[U.by_id[s]]["sector"] != rl.sector for s in w)
        elif rl.kind == "exclude_security":
            ok = rl.secid not in w
        elif rl.kind == "max_sector_share" and rl.value is not None:
            ok = sum(v for s, v in w.items() if U.secs[U.by_id[s]]["sector"] == rl.sector) <= rl.value + 0.005
        elif rl.kind == "max_drawdown_rub" and rl.value:
            ok = backtest(U, idx, x, amount)["max_dd_rub"] <= rl.value * 1.02
        out.append({"label": rl.label, "ok": bool(ok)})
    return out


def simulate_month(U: Universe, executed: dict, value: float, step: int) -> tuple[dict, float, dict]:
    """Двигаем веса портфеля по реальным недельным доходностям: квартал (13 недель) из последнего года истории."""
    T = U.R.shape[0]
    start = max(0, T - 52 + 13 * (step % 4))
    end = min(T, start + 13)
    new, total = {}, 0.0
    moves = {}
    for s, wgt in executed.items():
        i = U.by_id.get(s)
        if i is None:
            continue
        growth = float(np.prod(1 + U.R[start:end, i]))
        moves[s] = growth - 1
        new[s] = wgt * growth
        total += new[s]
    new = {s: v / total for s, v in new.items()}
    period = {"from": U.weeks[start] if U.weeks else "", "to": U.weeks[end - 1] if U.weeks else "",
              "portfolio_return": total - 1,
              "top_moves": sorted([{"secid": s, "return": round(r, 4)} for s, r in moves.items()],
                                  key=lambda d: -abs(d["return"]))[:3]}
    return new, value * total, period


def propose(U: Universe, prof: Profile, target: dict, current: dict | None, value: float) -> dict:
    T = np.array([prof.target[a] for a in AXES])
    W = np.array([prof.importance[a] for a in AXES])
    after = {h["secid"]: h["weight"] for h in target["holdings"]}
    _, _, vec_after = _vec(U, after)
    res = {
        "kind": "initial" if not current else "rebalance",
        "value": round(value),
        "mandate_target": prof.target,
        "after": [{"secid": s, "weight": w} for s, w in after.items()],
        "after_axes": dict(zip(AXES, vec_after.round(2).tolist())),
        "fit_after": round(fit_score(vec_after, T, W)),
        "checks_after": check_red_lines(U, prof, after, value),
    }
    if current:
        _, _, vec_before = _vec(U, current)
        res["before_axes"] = dict(zip(AXES, vec_before.round(2).tolist()))
        res["fit_before"] = round(fit_score(vec_before, T, W))
        res["checks_before"] = check_red_lines(U, prof, current, value)
    else:
        res["before_axes"] = None
        res["fit_before"] = None
        res["checks_before"] = []
    trades = []
    for s in sorted(set(after) | set(current or {})):
        w0, w1 = (current or {}).get(s, 0.0), after.get(s, 0.0)
        d = w1 - w0
        if abs(d) < 0.005:
            continue
        sec = U.secs[U.by_id[s]]
        rub = abs(d) * value
        lots = int(rub // (sec["price"] * (sec.get("lot") or 1)))
        if lots == 0:
            continue
        trades.append({"secid": s, "shortname": sec["shortname"], "side": "buy" if d > 0 else "sell",
                       "rub": round(rub), "lots": lots, "weight_from": round(w0, 4), "weight_to": round(w1, 4)})
    trades.sort(key=lambda t: (t["side"] != "sell", -t["rub"]))
    res["trades"] = trades
    res["all_ok"] = all(c["ok"] for c in res["checks_after"])
    return res
