"""Быстрая проверка: доступно ли API Мосбиржи (ISS) с этого компьютера и сколько бумаг можно подтянуть.

Запуск из корня проекта:  python scripts/check_iss.py
Ничего не сохраняет и не обращается к LLM. Делает около 10 запросов, занимает несколько секунд.
"""
import datetime as dt
import sys
import time

import httpx

ISS = "https://iss.moex.com/iss"
http = httpx.Client(timeout=20, headers={"User-Agent": "tinvest-premarket-mvp"})
ok_all = True


def check(title, path, params=None, block=None):
    global ok_all
    p = {"iss.meta": "off"}
    p.update(params or {})
    t = time.time()
    try:
        r = http.get(ISS + path, params=p)
        ms = int((time.time() - t) * 1000)
        r.raise_for_status()
        js = r.json()
        rows = js.get(block, {}).get("data", []) if block else []
        print(f"  ✓ {title}: {len(rows)} строк, {ms} мс")
        return js, rows
    except Exception as e:
        ok_all = False
        print(f"  ✕ {title}: {type(e).__name__}: {e}")
        return {}, []


print("Проверяю доступ к iss.moex.com…")
_, shares = check("Акции на основном режиме торгов (TQBR)", "/engines/stock/markets/shares/boards/TQBR/securities.json",
                  {"iss.only": "securities", "securities.columns": "SECID,SHORTNAME"}, "securities")
_, bonds = check("Облигации федерального займа (TQOB)", "/engines/stock/markets/bonds/boards/TQOB/securities.json",
                 {"iss.only": "securities", "securities.columns": "SECID,MATDATE"}, "securities")
ofz = [b for b in bonds if str(b[0]).startswith("SU26")]
start = (dt.date.today() - dt.timedelta(days=3 * 365)).isoformat()
for sec in ["SBER", "LKOH", "YDEX"]:
    check(f"Недельные цены {sec} за 3 года", f"/engines/stock/markets/shares/boards/TQBR/securities/{sec}/candles.json",
          {"interval": 7, "from": start}, "candles")
check("Дивиденды SBER", "/securities/SBER/dividends.json", block="dividends")
if ofz:
    check(f"Недельные цены {ofz[0][0]}", f"/engines/stock/markets/bonds/boards/TQOB/securities/{ofz[0][0]}/candles.json",
          {"interval": 7, "from": start}, "candles")

print()
if ok_all and shares:
    print(f"Готово: доступно {len(shares)} акций и {len(ofz)} ОФЗ с постоянным купоном.")
    print("Сборщик возьмёт из них 90 самых ликвидных акций и 10 ОФЗ.")
    print("Сначала можно собрать без LLM:  python scripts/build_universe.py --no-llm")
    print("Потом с карточками от LLM:      python scripts/build_universe.py")
else:
    print("Часть запросов не прошла. Проверьте интернет, VPN и прокси: ISS должен открываться в браузере —")
    print("  https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json")
    sys.exit(1)
