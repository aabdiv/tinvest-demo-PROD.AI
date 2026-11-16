"""Собирает базу бумаг из открытого API Мосбиржи (ISS, без ключа) и размечает её LLM.

Запуск из корня проекта:
    python scripts/build_universe.py              # ~90 акций + 10 ОФЗ, история за 3 года
    python scripts/build_universe.py --shares 60  # поменьше акций
    python scripts/build_universe.py --no-llm     # без карточек от LLM (только ручная разметка отраслей)

Результат: data/universe.json. Занимает 2–5 минут (сотни запросов к ISS).
"""
import argparse
import datetime as dt
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import config  # noqa: E402
from backend.axes import AXES, AXIS_METHOD, SECTORS  # noqa: E402
from scripts.sectors import SECTOR_OVERRIDES  # noqa: E402

ISS = "https://iss.moex.com/iss"
http = httpx.Client(timeout=30, headers={"User-Agent": "tinvest-premarket-mvp"})
TODAY = dt.date.today()


def get(path: str, params: dict | None = None) -> dict:
    p = {"iss.meta": "off"}
    p.update(params or {})
    for attempt in range(4):
        try:
            r = http.get(ISS + path, params=p)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    return {}


def rows(js: dict, block: str) -> list[dict]:
    b = js.get(block) or {}
    cols = b.get("columns", [])
    return [dict(zip(cols, r)) for r in b.get("data", [])]


def list_shares() -> list[dict]:
    js = get("/engines/stock/markets/shares/boards/TQBR/securities.json", {
        "iss.only": "securities,marketdata",
        "securities.columns": "SECID,SHORTNAME,SECNAME,LOTSIZE,PREVPRICE",
        "marketdata.columns": "SECID,LAST,ISSUECAPITALIZATION",
    })
    md = {r["SECID"]: r for r in rows(js, "marketdata")}
    out = []
    for s in rows(js, "securities"):
        m = md.get(s["SECID"], {})
        price = m.get("LAST") or s.get("PREVPRICE")
        if not price:
            continue
        out.append({
            "secid": s["SECID"], "shortname": s["SHORTNAME"], "name": s["SECNAME"] or s["SHORTNAME"],
            "lot": int(s.get("LOTSIZE") or 1), "price": float(price),
            "mcap": float(m.get("ISSUECAPITALIZATION") or 0), "kind": "share", "board": "TQBR",
        })
    return out


def list_ofz(n: int) -> list[dict]:
    js = get("/engines/stock/markets/bonds/boards/TQOB/securities.json", {
        "iss.only": "securities,marketdata",
        "securities.columns": "SECID,SHORTNAME,SECNAME,PREVPRICE,FACEVALUE,COUPONPERCENT,MATDATE,ACCRUEDINT",
        "marketdata.columns": "SECID,LAST,YIELD",
    })
    md = {r["SECID"]: r for r in rows(js, "marketdata")}
    cands = []
    for s in rows(js, "securities"):
        if not str(s["SECID"]).startswith("SU26"):  # ОФЗ-ПД: постоянный купон
            continue
        try:
            mat = dt.date.fromisoformat(s["MATDATE"])
        except Exception:
            continue
        if mat < TODAY + dt.timedelta(days=365):
            continue
        m = md.get(s["SECID"], {})
        pct = m.get("LAST") or s.get("PREVPRICE")
        if not pct:
            continue
        face = float(s.get("FACEVALUE") or 1000)
        y = m.get("YIELD") or s.get("COUPONPERCENT") or 0
        cands.append({
            "secid": s["SECID"], "shortname": s["SHORTNAME"], "name": s["SECNAME"] or s["SHORTNAME"],
            "lot": 1, "price": float(pct) / 100 * face + float(s.get("ACCRUEDINT") or 0),
            "yield": float(y) / 100, "maturity": s["MATDATE"], "mcap": 0.0, "kind": "bond", "board": "TQOB",
        })
    cands.sort(key=lambda c: c["maturity"])
    if len(cands) <= n:
        return cands
    idx = np.linspace(0, len(cands) - 1, n).round().astype(int)
    return [cands[i] for i in sorted(set(idx))]


def weekly_candles(sec: dict, start: str) -> list[tuple[str, float, float]]:
    market = "shares" if sec["kind"] == "share" else "bonds"
    path = f"/engines/stock/markets/{market}/boards/{sec['board']}/securities/{sec['secid']}/candles.json"
    out, offset = [], 0
    for _ in range(20):
        r = rows(get(path, {"interval": 7, "from": start, "start": offset}), "candles")
        if not r:
            break
        out += r
        offset += len(r)
    res = []
    for c in out:
        if c.get("close") and c.get("begin"):
            res.append((str(c["begin"])[:10], float(c["close"]), float(c.get("value") or 0)))
    return res


def dividends_12m(secid: str) -> float:
    try:
        js = get(f"/securities/{secid}/dividends.json")
    except Exception:
        return 0.0
    cutoff = (TODAY - dt.timedelta(days=365)).isoformat()
    total = 0.0
    for d in rows(js, "dividends"):
        date, val, cur = d.get("registryclosedate"), d.get("value"), d.get("currencyid")
        if date and val and str(date) >= cutoff and cur in (None, "SUR", "RUB", "RUR"):
            total += float(val)
    return total


def pct_rank(values: np.ndarray) -> np.ndarray:
    """Место бумаги среди всех: 0 — худшая, 1 — лучшая."""
    from scipy.stats import rankdata  # одинаковые значения получают одинаковый балл (например, нулевые дивиденды)
    return (rankdata(values, method="average") - 1) / max(len(values) - 1, 1)


def week_key(date_str: str) -> str:
    y, w, _ = dt.date.fromisoformat(date_str).isocalendar()
    return f"{y}-W{w:02d}"


def llm_cards(secs: list[dict]) -> dict:
    from backend import ai
    cards = {}
    for i in range(0, len(secs), 30):
        batch = secs[i : i + 30]
        try:
            got = ai.build_cards([{"secid": s["secid"], "name": s["name"], "kind": s["kind"]} for s in batch])
            cards.update({c["secid"]: c for c in got})
            print(f"  карточки: {len(cards)}/{len(secs)}")
        except Exception as e:
            print(f"  ! LLM не разметил пачку {i}: {e}")
    return cards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shares", type=int, default=90)
    ap.add_argument("--bonds", type=int, default=10)
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()

    start = (TODAY - dt.timedelta(days=365 * args.years + 7)).isoformat()
    print("1/5 Список акций и ОФЗ с Мосбиржи…")
    shares, bonds = list_shares(), list_ofz(args.bonds)
    print(f"  акций на TQBR: {len(shares)}, выбрано ОФЗ: {len(bonds)}")

    print("2/5 Недельные свечи за", args.years, "года…")
    allsecs = shares + bonds
    with ThreadPoolExecutor(6) as ex:
        candles = list(ex.map(lambda s: (s["secid"], weekly_candles(s, start)), allsecs))
    candles = dict(candles)

    # ликвидность: медиана недельного оборота за полгода
    for s in shares:
        vals = [v for _, _, v in candles.get(s["secid"], [])][-26:]
        s["liquidity"] = float(np.median(vals)) if vals else 0.0
    shares = [s for s in shares if len(candles.get(s["secid"], [])) >= 60]
    shares.sort(key=lambda s: s["liquidity"], reverse=True)
    shares = shares[: args.shares]
    bonds = [b for b in bonds if len(candles.get(b["secid"], [])) >= 60]
    for b in bonds:
        b["liquidity"] = 0.0
    secs = shares + bonds
    print(f"  в базу идут: {len(shares)} акций и {len(bonds)} ОФЗ")

    print("3/5 Дивиденды за 12 месяцев…")
    with ThreadPoolExecutor(6) as ex:
        divs = dict(ex.map(lambda s: (s["secid"], dividends_12m(s["secid"])), shares))
    for s in shares:
        s["div_yield"] = divs.get(s["secid"], 0.0) / s["price"] if s["price"] else 0.0
    for b in bonds:
        b["div_yield"] = b["yield"]

    print("4/5 Доходности и оси…")
    weeks = sorted({week_key(d) for s in secs for d, _, _ in candles[s["secid"]]})
    widx = {w: i for i, w in enumerate(weeks)}
    T = len(weeks)
    for s in secs:
        closes = np.full(T, np.nan)
        for d, c, _ in candles[s["secid"]]:
            closes[widx[week_key(d)]] = c
        r = closes[1:] / closes[:-1] - 1
        r = np.where(np.isfinite(r), r, 0.0)
        r = np.clip(r, -0.6, 1.5)  # защита от технических скачков (сплиты и т.п.)
        income = s["div_yield"] / 52
        s["weekly_returns"] = [round(float(x + income), 6) for x in r]
        valid = closes[np.isfinite(closes)]
        n_years = max(np.isfinite(closes).sum() / 52, 0.5)
        s["cagr"] = float((valid[-1] / valid[0]) ** (1 / n_years) - 1) if len(valid) > 1 else 0.0
        last = valid[-1]
        r13 = last / valid[-14] - 1 if len(valid) > 14 else 0.0
        r26 = last / valid[-27] - 1 if len(valid) > 27 else 0.0
        s["momentum"] = float(0.5 * r13 + 0.5 * r26)
        s["vol"] = float(np.std(r) * math.sqrt(52))

    cagr = np.array([s["cagr"] for s in secs])
    mom = np.array([s["momentum"] for s in secs])
    dy = np.array([s["div_yield"] for s in secs])
    vol = np.array([s["vol"] for s in secs])
    g, t, d, st = pct_rank(cagr), pct_rank(mom), pct_rank(dy), 1 - pct_rank(vol)
    sh_idx = [i for i, s in enumerate(secs) if s["kind"] == "share"]
    mc = np.array([math.log(max(secs[i]["mcap"], 1)) for i in sh_idx])
    lq = np.array([math.log(max(secs[i]["liquidity"], 1)) for i in sh_idx])
    q_sh = 0.6 * pct_rank(mc) + 0.4 * pct_rank(lq)
    q = np.ones(len(secs))
    for j, i in enumerate(sh_idx):
        q[i] = q_sh[j]
    for i, s in enumerate(secs):
        s["axes"] = {
            "growth": round(10 * g[i], 1), "trend": round(10 * t[i], 1), "dividends": round(10 * d[i], 1),
            "stability": round(10 * st[i], 1), "quality": round(10 * q[i], 1),
        }

    print("5/5 Карточки бумаг (отрасль, описание, теги)…")
    cards = {} if (args.no_llm or config.MOCK) else llm_cards(secs)
    for s in secs:
        c = cards.get(s["secid"], {})
        if s["kind"] == "bond":
            s["sector"] = "gov_bonds"
        else:
            s["sector"] = SECTOR_OVERRIDES.get(s["secid"]) or (c.get("sector") if c.get("sector") in SECTORS else "other")
        s["description"] = c.get("description") or (f"ОФЗ с погашением {s.get('maturity')}" if s["kind"] == "bond" else "")
        s["tags"] = c.get("tags") or []

    keep = ["secid", "shortname", "name", "kind", "sector", "description", "tags", "price", "lot", "mcap",
            "liquidity", "div_yield", "cagr", "momentum", "vol", "axes", "weekly_returns", "maturity"]
    out = {
        "built_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "Московская биржа, ISS API (iss.moex.com)",
        "weeks": weeks[1:],
        "axis_method": AXIS_METHOD,
        "securities": [{k: s.get(k) for k in keep} for s in secs],
    }
    path = ROOT / "data" / "universe.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"Готово: {path} ({len(secs)} бумаг, {len(weeks) - 1} недель)")


if __name__ == "__main__":
    main()
