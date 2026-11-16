"""ТОЛЬКО ДЛЯ ТЕСТОВ: синтетическая база с выдуманными бумагами (не настоящие данные).
Создаёт tests/universe.fake.json, чтобы проверить приложение без доступа к Мосбирже."""
import json, math, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.axes import SECTORS
rng = np.random.default_rng(7)
T = 156
market = rng.normal(0.002, 0.03, T)
secs = []
plan = [("banks_finance", 8), ("oil_gas", 8), ("metals_mining", 7), ("it_internet", 8), ("telecom", 3),
        ("consumer_retail", 6), ("utilities", 6), ("chemicals", 3), ("real_estate", 3), ("transport", 3), ("gov_bonds", 8)]
for sector, n in plan:
    for k in range(n):
        bond = sector == "gov_bonds"
        beta = 0.1 if bond else rng.uniform(0.6, 1.4)
        idio = 0.004 if bond else rng.uniform(0.015, 0.05)
        drift = rng.uniform(-0.001, 0.004)
        r = beta * market + rng.normal(drift, idio, T)
        div = rng.uniform(0.11, 0.15) if bond else (rng.uniform(0.0, 0.03) if sector == "it_internet" else rng.uniform(0.02, 0.13))
        secs.append({"secid": f"TST{len(secs):02d}", "shortname": f"Тест-{SECTORS[sector][:8]}-{k+1}",
                     "name": f"Тестовая бумага {len(secs)} ({SECTORS[sector]})", "kind": "bond" if bond else "share",
                     "sector": sector, "description": "Синтетическая бумага для теста", "tags": [SECTORS[sector].lower()],
                     "price": float(rng.uniform(50, 3000)), "lot": int(rng.choice([1, 10, 100])), "mcap": float(rng.uniform(1e10, 5e12)),
                     "liquidity": float(rng.uniform(1e7, 1e10)), "div_yield": float(div),
                     "weekly_returns": [round(float(x + div / 52), 6) for x in r], "maturity": "2030-01-01" if bond else None,
                     "_r": r})
def rank(v): o = np.argsort(np.argsort(v)).astype(float); return o / (len(v) - 1)
cagr = np.array([np.prod(1 + s["_r"]) ** (1 / 3) - 1 for s in secs]); mom = np.array([s["_r"][-26:].sum() for s in secs])
dy = np.array([s["div_yield"] for s in secs]); vol = np.array([s["_r"].std() * math.sqrt(52) for s in secs])
mc = np.array([math.log(s["mcap"]) for s in secs])
for i, s in enumerate(secs):
    s["cagr"], s["momentum"], s["vol"] = float(cagr[i]), float(mom[i]), float(vol[i])
    q = 1.0 if s["kind"] == "bond" else rank(mc)[i]
    s["axes"] = {"growth": round(10 * rank(cagr)[i], 1), "trend": round(10 * rank(mom)[i], 1), "dividends": round(10 * rank(dy)[i], 1),
                 "stability": round(10 * (1 - rank(vol)[i]), 1), "quality": round(10 * q, 1)}
    del s["_r"]
out = {"built_at": "ТЕСТОВЫЕ ДАННЫЕ", "source": "синтетика для тестов", "weeks": [f"2024-W{(i % 52) + 1:02d}" for i in range(T)], "securities": secs}
(ROOT / "tests" / "universe.fake.json").write_text(json.dumps(out, ensure_ascii=False))
print("ok", len(secs))
