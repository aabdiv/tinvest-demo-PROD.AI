"""Прогон всего пользовательского пути через API в тестовом режиме (MOCK, синтетическая база)."""
import os, sys, json, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
os.environ["MOCK_LLM"] = "1"
os.environ["UNIVERSE_PATH"] = str(ROOT / "tests" / "universe.fake.json")
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend.main import app
c = TestClient(app)
def post(path, **body):
    t = time.time(); r = c.post(path, json=body); dt = (time.time() - t) * 1000
    assert r.status_code == 200, (path, r.status_code, r.text[:500])
    print(f"{path:22s} {dt:6.0f} мс"); return r.json()
print(c.get("/api/meta").json()["universe"])
state = {}
j = post("/api/interpret", state=state, text="Хочу стабильные дивиденды, чтобы через 5 лет был дополнительный доход. Нефть не хочу. Боюсь повторения 2022 года. Верю в российский IT.")
state = j["state"]; print(" чипы:", [w["label"] for w in state["wishes"]]); print(" конфликты:", [x["text"] for x in state["conflicts"]])
j = post("/api/recompute", state=state); state = j["state"]; p = j["portfolio"]
print(" цель", p["target"]); print(" вышло", p["achieved"], "fit", p["fit"]); print(" метрики", p["metrics"]); print(" заметки", p["notes"])
print(" бумаги", [(h["shortname"], h["weight"], h["sector"]) for h in p["holdings"]][:12])
assert all(h["sector"] != "oil_gas" for h in p["holdings"]), "нефть в портфеле!"
assert max(h["weight"] for h in p["holdings"]) <= 0.1201
conf = state["conflicts"][0]
j = post("/api/interpret", state=state, text="Выбираю: " + conf["options"][0], conflict_id=conf["id"]); state = j["state"]
state["manual_axes"]["growth"] = 7.5
j = post("/api/recompute", state=state); p = j["portfolio"]; print(" после правки роста:", p["achieved"], "fit", p["fit"])
j = post("/api/redline", state=state, text="не больше 15% в банках"); state = j["state"]; print(" +линия", state["manual_red_lines"][-1]["label"])
j = post("/api/mandate", state=state); print(" мандат:", j["mandate"])
j = post("/api/recompute", state=state); p = j["portfolio"]
sec = p["holdings"][0]["secid"]; j = post("/api/explain", state=state, secid=sec); print(" объяснение:", j["text"])
j = post("/api/theme", state=state, text="банки"); state = j["state"]
j = post("/api/agent/propose", state=state); prop = j["proposal"]; print(" первичная покупка: сделок", len(prop["trades"]), "ok", prop["all_ok"])
j = post("/api/agent/confirm", state=state, after=prop["after"]); state = j["state"]
for step in range(3):
    j = post("/api/agent/simulate", state=state); state = j["state"]; prop = j["proposal"]
    print(f" месяц {step+1}: {j['period']['portfolio_return']*100:+.1f}%, fit {prop['fit_before']}→{prop['fit_after']}, сделок {len(prop['trades'])}, auto={j['applied']}")
    if step == 1: state["autonomy"] = "auto"
    elif not j["applied"]:
        j = post("/api/agent/confirm", state=state, after=prop["after"]); state = j["state"]
print(" журнал:", [e["text"] for e in state["agent_log"]])
print("OK")
