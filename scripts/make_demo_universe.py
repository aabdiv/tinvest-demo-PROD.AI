"""Демо-база без доступа к Мосбирже: 30 реальных компаний и ОФЗ с УСЛОВНЫМИ цифрами.

Отрасли и описания — общая информация о компаниях. Цены, дивиденды и история за 3 года — условные:
недельные доходности сгенерированы так, чтобы совпадать с качественным профилем бумаги
(«высокие дивиденды», «сильно колеблется», «росла», «падает последние полгода»).
Это не котировки и не прогноз. Интерфейс показывает пометку «демо-данные».

Запуск из корня проекта:  python scripts/make_demo_universe.py   → data/universe.json
"""
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parent.parent
WEEKS = 157
DIV = {"none": 0.0, "low": 0.02, "mid": 0.06, "high": 0.11}
VOL = {"low": 0.18, "mid": 0.26, "high": 0.38}
GROW = {"neg": -0.08, "low": 0.0, "mid": 0.08, "high": 0.18}
TREND = {"down": -0.12, "flat": 0.0, "up": 0.12}
BETA = {"banks_finance": 1.1, "oil_gas": 0.9, "metals_mining": 1.0, "it_internet": 1.3, "telecom": 0.7,
        "consumer_retail": 0.8, "utilities": 0.7, "chemicals": 0.7, "real_estate": 1.3, "transport": 1.2,
        "healthcare": 0.9, "gov_bonds": 0.15}

# тикер, название, отрасль, описание, дивиденды, колебания, рост, последние полгода, размер 1–10, условная цена, лот
SHARES = [
    ("SBER", "Сбербанк", "banks_finance", "Крупнейший банк России", "high", "mid", "mid", "up", 10, 300, 1),
    ("VTBR", "ВТБ", "banks_finance", "Второй по величине банк страны, госбанк", "mid", "high", "low", "down", 8, 90, 1),
    ("T", "Т-Технологии", "banks_finance", "Экосистема Т-Банка: банк, брокер, сервисы", "low", "high", "high", "up", 8, 3000, 1),
    ("MOEX", "Мосбиржа", "banks_finance", "Главная биржевая площадка России", "high", "mid", "mid", "flat", 6, 200, 10),
    ("LKOH", "Лукойл", "oil_gas", "Крупная частная нефтяная компания", "high", "mid", "mid", "flat", 9, 7000, 1),
    ("ROSN", "Роснефть", "oil_gas", "Крупнейшая нефтяная госкомпания", "mid", "mid", "low", "down", 9, 550, 1),
    ("GAZP", "Газпром", "oil_gas", "Газовая госкомпания, добыча и экспорт газа", "none", "mid", "neg", "down", 9, 130, 10),
    ("NVTK", "Новатэк", "oil_gas", "Газ и сжиженный природный газ", "mid", "mid", "low", "down", 8, 1100, 1),
    ("TATN", "Татнефть", "oil_gas", "Нефтяная компания Татарстана", "high", "mid", "mid", "flat", 7, 650, 1),
    ("GMKN", "Норникель", "metals_mining", "Никель, палладий, медь", "low", "mid", "neg", "down", 8, 120, 10),
    ("PLZL", "Полюс", "metals_mining", "Крупнейший золотодобытчик России", "mid", "mid", "high", "up", 8, 2000, 1),
    ("ALRS", "Алроса", "metals_mining", "Добыча алмазов", "low", "mid", "neg", "down", 6, 50, 10),
    ("CHMF", "Северсталь", "metals_mining", "Металлургия, производство стали", "mid", "mid", "low", "down", 7, 1200, 1),
    ("YDEX", "Яндекс", "it_internet", "Поиск, такси, доставка, облачные сервисы", "low", "high", "high", "up", 9, 4000, 1),
    ("OZON", "Ozon", "it_internet", "Маркетплейс и финтех", "none", "high", "high", "up", 7, 4000, 1),
    ("POSI", "Positive Technologies", "it_internet", "Кибербезопасность, отечественное ПО", "mid", "high", "low", "down", 5, 1200, 1),
    ("HEAD", "Хэдхантер", "it_internet", "Сервис поиска работы и сотрудников", "high", "mid", "mid", "flat", 5, 3500, 1),
    ("ASTR", "Астра", "it_internet", "Отечественные операционные системы", "mid", "high", "neg", "down", 4, 350, 1),
    ("MTSS", "МТС", "telecom", "Мобильная связь и цифровые сервисы", "high", "low", "low", "flat", 7, 220, 10),
    ("X5", "X5", "consumer_retail", "Крупнейшая сеть продуктовых магазинов", "high", "mid", "mid", "up", 8, 3000, 1),
    ("MGNT", "Магнит", "consumer_retail", "Сеть продуктовых магазинов", "mid", "mid", "neg", "down", 7, 4000, 1),
    ("IRAO", "Интер РАО", "utilities", "Производство и сбыт электроэнергии", "mid", "low", "low", "flat", 7, 3.5, 100),
    ("HYDR", "РусГидро", "utilities", "Гидроэлектростанции, госкомпания", "low", "low", "neg", "down", 6, 0.5, 1000),
    ("PHOR", "ФосАгро", "chemicals", "Фосфорные удобрения, экспорт", "high", "low", "low", "flat", 7, 6500, 1),
    ("PIKK", "ПИК", "real_estate", "Крупный застройщик жилья", "none", "high", "neg", "down", 5, 500, 1),
    ("SMLT", "Самолёт", "real_estate", "Застройщик жилья", "none", "high", "neg", "down", 4, 1200, 1),
    ("AFLT", "Аэрофлот", "transport", "Крупнейшая авиакомпания страны", "low", "high", "high", "up", 6, 60, 10),
    ("MDMG", "Мать и дитя", "healthcare", "Сеть частных клиник и госпиталей", "mid", "mid", "high", "up", 4, 1300, 1),
]
# тикер, название, описание, доходность, колебания, рост цены, последние полгода, условная цена
BONDS = [
    ("OFZ-2Y", "ОФЗ короткие", "Гособлигации с погашением примерно через 2 года", 0.14, 0.04, 0.01, "flat", 950),
    ("OFZ-6Y", "ОФЗ средние", "Гособлигации с погашением примерно через 6 лет", 0.14, 0.08, 0.0, "flat", 900),
    ("OFZ-15Y", "ОФЗ длинные", "Гособлигации с погашением примерно через 15 лет", 0.14, 0.13, -0.02, "up", 700),
]


def make_series(rng, market, beta, vol, cagr, m26):
    sw = vol / math.sqrt(52)
    mk = market * beta
    idio_sd = math.sqrt(max(sw ** 2 - (beta * market.std()) ** 2, (0.25 * sw) ** 2))
    lr = mk + rng.normal(0, idio_sd, len(market))
    lr = (lr - lr.mean()) / lr.std() * sw
    n = len(lr)
    head, tail = lr[: n - 26], lr[n - 26:]
    total = 3 * math.log(1 + cagr)
    last = math.log(1 + m26)
    head += (total - last - head.sum()) / len(head)
    tail += (last - tail.sum()) / len(tail)
    return np.exp(np.concatenate([head, tail])) - 1


def pct_rank(v):
    return (rankdata(v, method="average") - 1) / max(len(v) - 1, 1)


def main():
    rng = np.random.default_rng(2026)
    market = rng.normal(0, 0.2 / math.sqrt(52), WEEKS - 1)
    today = dt.date.today()
    weeks = []
    for k in range(WEEKS - 1, 0, -1):
        y, w, _ = (today - dt.timedelta(weeks=k - 1)).isocalendar()
        weeks.append(f"{y}-W{w:02d}")
    secs = []
    for secid, name, sector, desc, div, vol, grow, trend, size, price, lot in SHARES:
        r = make_series(rng, market, BETA[sector], VOL[vol], GROW[grow], TREND[trend])
        secs.append({"secid": secid, "shortname": name, "name": name, "kind": "share", "sector": sector,
                     "description": desc, "tags": [], "price": float(price), "lot": lot,
                     "mcap": 10 ** (9 + size * 0.35), "liquidity": 10 ** (6 + size * 0.4),
                     "div_yield": DIV[div], "_r": r})
    for secid, name, desc, y, vol, grow, trend, price in BONDS:
        r = make_series(rng, market, BETA["gov_bonds"], vol, grow, TREND[trend] / 3)
        secs.append({"secid": secid, "shortname": name, "name": name, "kind": "bond", "sector": "gov_bonds",
                     "description": desc, "tags": ["госдолг", "купоны"], "price": float(price), "lot": 1,
                     "mcap": 0.0, "liquidity": 0.0, "div_yield": y, "_r": r, "maturity": None})
    for s in secs:
        r = s["_r"]
        closes = np.cumprod(1 + r)
        s["cagr"] = float(closes[-1] ** (1 / 3) - 1)
        s["momentum"] = float(0.5 * (closes[-1] / closes[-14] - 1) + 0.5 * (closes[-1] / closes[-27] - 1))
        s["vol"] = float(r.std() * math.sqrt(52))
        s["weekly_returns"] = [round(float(x + s["div_yield"] / 52), 6) for x in r]
    g = pct_rank(np.array([s["cagr"] for s in secs]))
    t = pct_rank(np.array([s["momentum"] for s in secs]))
    d = pct_rank(np.array([s["div_yield"] for s in secs]))
    st = 1 - pct_rank(np.array([s["vol"] for s in secs]))
    sh = [i for i, s in enumerate(secs) if s["kind"] == "share"]
    q_sh = pct_rank(np.array([math.log(secs[i]["mcap"]) for i in sh]))
    q = np.ones(len(secs))
    for j, i in enumerate(sh):
        q[i] = q_sh[j]
    for i, s in enumerate(secs):
        s["axes"] = {"growth": round(10 * g[i], 1), "trend": round(10 * t[i], 1), "dividends": round(10 * d[i], 1),
                     "stability": round(10 * st[i], 1), "quality": round(10 * q[i], 1)}
        del s["_r"]
    out = {
        "built_at": "ДЕМО " + today.isoformat(),
        "demo": True,
        "source": "ДЕМО: реальные компании, но цены, дивиденды и история условные",
        "weeks": weeks,
        "securities": secs,
    }
    path = ROOT / "data" / "universe.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"Готово: {path} — {len(secs)} бумаг (демо-данные)")


if __name__ == "__main__":
    main()
