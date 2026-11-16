"""Проверки без сети: 1) цепочка запасных режимов LLM; 2) сборщик базы на ответах в формате ISS."""
import json, os, sys, random, datetime as dt
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["OPENROUTER_API_KEY"] = "test"
from backend import llm, config
config.MOCK = False

# 1) LLM: первые два варианта падают, третий (json_object) отвечает текстом с ```json
calls = []
class FakeCompletions:
    def create(self, **kw):
        calls.append((kw["response_format"]["type"], "reasoning" in kw["extra_body"]))
        if len(calls) < 3: raise RuntimeError("404 no endpoints support response_format")
        msg = SimpleNamespace(content='```json\n{"text": "ок"}\n```')
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], model="x/y", provider="Prov")
llm._client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
data, meta = llm.structured("fast", "s", "u", "t", {"type": "object"})
assert data == {"text": "ок"} and meta["mode"] == "json_object", (data, meta)
print("LLM fallback ok:", calls, meta)

# 2) Сборщик: подменяем get() ответами в формате ISS
import scripts.build_universe as B
random.seed(1)
shares = [("SBER", "Сбербанк"), ("GAZP", "Газпром"), ("YDEX", "Яндекс"), ("MGNT", "Магнит"), ("ZZZZ", "Неизвестная")]
def fake_get(path, params=None):
    params = params or {}
    if path.endswith("TQBR/securities.json"):
        return {"securities": {"columns": ["SECID","SHORTNAME","SECNAME","LOTSIZE","PREVPRICE"], "data": [[s, n, n + " ПАО", 10, 100.0] for s, n in shares]},
                "marketdata": {"columns": ["SECID","LAST","ISSUECAPITALIZATION"], "data": [[s, 101.0, 1e12] for s, _ in shares]}}
    if path.endswith("TQOB/securities.json"):
        return {"securities": {"columns": ["SECID","SHORTNAME","SECNAME","PREVPRICE","FACEVALUE","COUPONPERCENT","MATDATE","ACCRUEDINT"],
                               "data": [["SU26238RMFS4","ОФЗ 26238","ОФЗ-ПД 26238",60.0,1000,7.1,"2041-05-15",5.0], ["SU26240RMFS0","ОФЗ 26240","x",62.0,1000,7.0,"2036-07-30",1.0], ["SU25084RMFS3","ОФЗ 25084","x",99.0,1000,5.3,"2026-10-01",1.0]]},
                "marketdata": {"columns": ["SECID","LAST","YIELD"], "data": [["SU26238RMFS4",60.5,14.2],["SU26240RMFS0",62.5,14.0]]}}
    if "/candles.json" in path:
        if params.get("start", 0) > 0: return {"candles": {"columns": [], "data": []}}
        d0 = dt.date.today() - dt.timedelta(days=3*365)
        data, price = [], 100.0
        for k in range(157):
            price *= 1 + random.gauss(0.002, 0.04)
            day = d0 + dt.timedelta(weeks=k); day -= dt.timedelta(days=day.weekday())
            data.append([price, price, price, price, 1e8 * random.random(), 1000, f"{day} 00:00:00", f"{day} 23:59:59"])
        return {"candles": {"columns": ["open","close","high","low","value","volume","begin","end"], "data": data}}
    if "/dividends.json" in path:
        recent = (dt.date.today() - dt.timedelta(days=100)).isoformat()
        return {"dividends": {"columns": ["secid","isin","registryclosedate","value","currencyid"], "data": [[path.split("/")[2], "x", recent, 12.5, "RUB"]]}}
    raise AssertionError(path)
B.get = fake_get
config.MOCK = True
out_path = ROOT / "data" / "universe.json"
backup = out_path.read_bytes() if out_path.exists() else None
sys.argv = ["x", "--shares", "4", "--bonds", "2", "--no-llm"]
B.main()
u = json.loads(out_path.read_text())
print("секторы:", {s["secid"]: s["sector"] for s in u["securities"]})
print("оси SBER:", u["securities"][0]["axes"], "div_yield", round(u["securities"][0]["div_yield"], 3))
assert len(u["securities"]) == 6 and all(len(s["weekly_returns"]) == len(u["weeks"]) for s in u["securities"])
if backup is None: out_path.unlink()
else: out_path.write_bytes(backup)
print("OK")
