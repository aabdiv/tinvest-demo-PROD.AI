"""FastAPI-бэкенд MVP. Запуск: uvicorn backend.main:app --reload"""
import datetime as dt
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import ai, config
from .agent import propose, simulate_month
from .axes import AXES, AXIS_METHOD, AXIS_RU, SECTORS
from .llm import LLMError
from .optimizer import fit_score, optimize
from .profile import all_red_lines, all_themes, fold
from .schemas import Conflict, Holding, RedLine, Req, State, Theme, Wish
from .universe import get_universe

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
app = FastAPI(title="T-Invest Premarket MVP")
FRONT = config.ROOT / "frontend"


# ---------------------------------------------------------------- helpers
def nid(state: State, prefix: str) -> str:
    state.seq += 1
    return f"{prefix}{state.seq}"


def summary(state: State) -> dict:
    p = fold(state)
    return {
        "target": {AXIS_RU[a]: v for a, v in p.target.items()},
        "red_lines": [l.label for l in p.red_lines],
        "themes": [t.query for t in p.themes],
        "amount_rub": state.amount_rub, "horizon_years": state.horizon_years,
        "earlier_wishes": [w.label for w in state.wishes if w.status == "accepted"][-12:],
    }


def safe_llm(fn, *args):
    try:
        return fn(*args)
    except LLMError as e:
        raise HTTPException(502, str(e))


def apply_interpret(state: State, text: str, data: dict) -> list[str]:
    new_ids = []
    for item in data.get("wishes", []):
        typ = item.get("type", "other")
        effects = {a: max(-3, min(3, int(item.get(a) or 0))) for a in AXES if int(item.get(a) or 0)}
        span = (item.get("span") or "")[:120]
        w = Wish(id=nid(state, "w"), span=span, label=(item.get("label") or span)[:40], type=typ,
                 effects=effects, confidence=float(item.get("confidence") or 0.7))
        kind = item.get("rl_kind", "none")
        if kind and kind != "none":
            val = float(item.get("rl_value") or 0) or None
            if kind in ("max_position", "max_sector_share") and val and val > 1:
                val = val / 100
            sector = item.get("rl_sector") if item.get("rl_sector") in SECTORS else None
            w.red_line = RedLine(id=nid(state, "r"), kind=kind, sector=sector,
                                 secid=(item.get("rl_secid") or None), value=val,
                                 label=item.get("label") or kind, source=f"из ваших слов: «{span}»")
            w.type = "red_line" if typ not in ("fear",) else typ
        if item.get("theme_query"):
            share = float(item.get("theme_max_share") or 0.1)
            share = share / 100 if share > 1 else share
            w.theme = Theme(id=nid(state, "t"), query=item["theme_query"], max_share=max(0.02, min(0.5, share)),
                            source=f"из ваших слов: «{span}»")
            # новая формулировка той же темы заменяет старую (например, после решения противоречия)
            words = {x for x in item["theme_query"].lower().split() if len(x) > 2}
            for old in all_themes(state):
                if old.active and words & {x for x in old.query.lower().split() if len(x) > 2}:
                    old.active = False
        if item.get("horizon_years"):
            state.horizon_years = max(1, min(30, int(item["horizon_years"])))
            w.horizon_years = state.horizon_years
        if item.get("amount_rub"):
            state.amount_rub = max(10_000, float(item["amount_rub"]))
            w.amount_rub = state.amount_rub
        state.wishes.append(w)
        new_ids.append(w.id)
    for c in data.get("contradictions", []):
        opts = [o for o in [c.get("option_a"), c.get("option_b")] if o]
        if c.get("text") and opts:
            state.conflicts.append(Conflict(id=nid(state, "c"), text=c["text"], options=opts))
    state.messages.append(text)
    return new_ids


def resolve_themes(state: State, U) -> list[dict]:
    metas = []
    cards = [U.card(i) for i in range(U.N)]
    for th in all_themes(state):
        if th.resolved or not th.active:
            continue
        data, meta = safe_llm(ai.resolve_theme, th.query, cards)
        metas.append({**meta, "what": f"поиск по теме «{th.query}»"})
        th.matches = [{"secid": m["secid"], "relevance": max(0.0, min(1.0, float(m.get("relevance", 0.5)))),
                       "why": m.get("why", "")} for m in data.get("matches", []) if m.get("secid") in U.by_id]
        th.resolved = True
    return metas


def compute(state: State) -> tuple[dict, list[dict]]:
    U = get_universe()
    metas = resolve_themes(state, U)
    prof = fold(state)
    res = optimize(U, prof)
    res["red_lines"] = [l.model_dump() for l in all_red_lines(state)]
    res["themes"] = [t.model_dump() for t in all_themes(state)]
    res["pinned"] = prof.pinned
    return res, metas


def mandate_facts(state: State, res: dict) -> dict:
    return {
        "horizon_years": state.horizon_years, "amount_rub": state.amount_rub,
        "target": {AXIS_RU[a]: v for a, v in res["target"].items()},
        "achieved": {AXIS_RU[a]: v for a, v in res["achieved"].items()},
        "top_sectors": [{"name": s["name"], "share_pct": round(100 * s["weight"])} for s in res["sectors"][:4]],
        "red_lines": [l["label"] for l in res["red_lines"] if l["active"]],
        "drawdown_limit_rub": res["metrics"]["dd_limit_rub"],
        "themes": [t["query"] for t in res["themes"] if t["active"]],
        "history_3y": {"годовая_доходность_pct": round(100 * res["metrics"]["ann_return"], 1),
                       "худшая_просадка_rub": res["metrics"]["max_dd_rub"]},
    }


def out(state: State, **kw) -> dict:
    return {"state": state.model_dump(), **kw}


# ---------------------------------------------------------------- API
@app.get("/api/meta")
def meta():
    try:
        U = get_universe()
        uni = {"count": U.N, "built_at": U.meta.get("built_at"), "source": U.meta.get("source"),
               "weeks": len(U.weeks), "ok": True, "demo": bool(U.meta.get("demo"))}
    except FileNotFoundError as e:
        uni = {"ok": False, "error": str(e)}
    return {"axes": AXES, "axis_ru": AXIS_RU, "axis_method": AXIS_METHOD, "sectors": SECTORS, "universe": uni,
            "mock": config.MOCK, "fast_model": config.FAST_MODEL, "smart_model": config.SMART_MODEL}


@app.get("/api/universe")
def universe():
    return get_universe().public()


@app.post("/api/interpret")
def interpret(req: Req):
    state, text = req.state, (req.text or "").strip()
    if not text:
        raise HTTPException(400, "Пустой текст")
    if req.conflict_id:
        for c in state.conflicts:
            if c.id == req.conflict_id:
                c.resolved = True
    data, m = safe_llm(ai.interpret, text, summary(state))
    new_ids = apply_interpret(state, text, data)
    return out(state, new_ids=new_ids, reply=data.get("reply", ""), llm=[{**m, "what": "разбор пожеланий"}])


@app.post("/api/recompute")
def recompute(req: Req):
    res, metas = compute(req.state)
    return out(req.state, portfolio=res, llm=metas)


@app.post("/api/mandate")
def mandate(req: Req):
    res, _ = compute(req.state)
    if "error" in res:
        return {"mandate": res["error"], "llm": []}
    data, m = safe_llm(ai.write_mandate, mandate_facts(req.state, res))
    return {"mandate": data.get("mandate", ""), "llm": [{**m, "what": "мандат"}]}


@app.post("/api/explain")
def explain(req: Req):
    U = get_universe()
    i = U.by_id.get(req.secid or "")
    if i is None:
        raise HTTPException(404, "Нет такой бумаги")
    res, _ = compute(req.state)
    s = U.secs[i]
    T = res["target"]
    gaps = {a: abs(s["axes"][a] - T[a]) * res["importance"][a] for a in AXES}
    g = max(gaps, key=gaps.get)
    held = next((h for h in res["holdings"] if h["secid"] == s["secid"]), None)
    theme_why = [m["why"] for t in res["themes"] for m in t["matches"] if m["secid"] == s["secid"]]
    facts = {
        "бумага": f"{s['shortname']} ({s['name']})", "отрасль": SECTORS.get(s["sector"]), "описание": s.get("description"),
        "оси_бумаги": {AXIS_RU[a]: s["axes"][a] for a in AXES}, "цель_клиента": {AXIS_RU[a]: T[a] for a in AXES},
        "в_портфеле": f"{round(100 * held['weight'])}%" if held else "нет",
        "почему_по_теме": theme_why[:1], "fit": next((h["fit"] for h in res["holdings"] + res["candidates"] if h["secid"] == s["secid"]), None),
        "biggest_gap": {"axis": AXIS_RU[g], "security": s["axes"][g], "target": T[g]},
    }
    if facts["fit"] is None:
        import numpy as np
        facts["fit"] = round(fit_score(np.array([s["axes"][a] for a in AXES]), np.array([T[a] for a in AXES]),
                                       np.array([res["importance"][a] for a in AXES])))
    data, m = safe_llm(ai.explain_security, facts)
    return {"text": data.get("text", ""), "biggest_gap": g, "llm": [{**m, "what": "объяснение бумаги"}]}


@app.post("/api/redline")
def add_red_line(req: Req):
    state, text = req.state, (req.text or "").strip()
    data, m = safe_llm(ai.parse_red_line, text)
    kind = data.get("rl_kind", "none")
    if kind == "none":
        return out(state, added=False, message="Не похоже на запрет. Попробуйте «без банков» или «не больше 10% в IT».",
                   llm=[{**m, "what": "красная линия"}])
    val = float(data.get("rl_value") or 0) or None
    if kind in ("max_position", "max_sector_share") and val and val > 1:
        val /= 100
    state.manual_red_lines.append(RedLine(
        id=nid(state, "r"), kind=kind, sector=data.get("rl_sector") if data.get("rl_sector") in SECTORS else None,
        secid=data.get("rl_secid") or None, value=val, label=data.get("label") or text[:35], source=f"добавлено: «{text[:60]}»"))
    return out(state, added=True, llm=[{**m, "what": "красная линия"}])


@app.post("/api/theme")
def add_theme(req: Req):
    state, text = req.state, (req.text or "").strip()
    if not text:
        raise HTTPException(400, "Пустая тема")
    state.manual_themes.append(Theme(id=nid(state, "t"), query=text, max_share=0.1, source="поиск по смыслу"))
    res, metas = compute(state)
    return out(state, portfolio=res, llm=metas)


@app.post("/api/agent/propose")
def agent_propose(req: Req):
    state = req.state
    U = get_universe()
    res, metas = compute(state)
    if "error" in res:
        raise HTTPException(400, res["error"])
    current = {h.secid: h.weight for h in state.executed} if state.executed else None
    value = state.executed_value or state.amount_rub
    prop = propose(U, fold(state), res, current, value)
    metas += _rationale(prop)
    return out(state, proposal=prop, llm=metas)


@app.post("/api/agent/confirm")
def agent_confirm(req: Req):
    state = req.state
    if not req.after:
        raise HTTPException(400, "Нет итоговых долей")
    first = state.executed is None
    state.executed = [Holding(secid=h.secid, weight=h.weight) for h in req.after]
    if first:
        state.executed_value = state.amount_rub
    state.agent_log.append({"at": dt.datetime.now().strftime("%H:%M:%S"), "type": "confirmed",
                            "text": "Портфель собран агентом" if first else "Ребалансировка подтверждена"})
    return out(state)


@app.post("/api/agent/simulate")
def agent_simulate(req: Req):
    state = req.state
    if not state.executed:
        raise HTTPException(400, "Сначала доверьте портфель агенту")
    U = get_universe()
    cur = {h.secid: h.weight for h in state.executed}
    new, value, period = simulate_month(U, cur, state.executed_value or state.amount_rub, state.sim_step)
    state.sim_step += 1
    state.executed = [Holding(secid=s, weight=w) for s, w in new.items()]
    state.executed_value = value
    res, metas = compute(state)
    prop = propose(U, fold(state), res, new, value)
    metas += _rationale(prop)
    applied = False
    entry = {"at": dt.datetime.now().strftime("%H:%M:%S"), "type": "month",
             "text": f"Прошёл квартал рынка ({period['from']} — {period['to']}): портфель {period['portfolio_return'] * 100:+.1f}%"}
    state.agent_log.append(entry)
    if state.autonomy == "auto" and prop["all_ok"] and prop["trades"]:
        state.executed = [Holding(secid=h["secid"], weight=h["weight"]) for h in prop["after"]]
        state.agent_log.append({"at": entry["at"], "type": "auto",
                                "text": f"Агент сам провёл ребалансировку: {len(prop['trades'])} сделок, совпадение "
                                        f"{prop['fit_before']}% → {prop['fit_after']}%"})
        applied = True
    return out(state, proposal=prop, period=period, applied=applied, llm=metas)


def _rationale(prop: dict) -> list[dict]:
    if not prop["trades"]:
        prop["rationale"] = "Портфель и так соответствует мандату, сделки не нужны."
        return []
    facts = {"тип": "первичная покупка" if prop["kind"] == "initial" else "ребалансировка",
             "fit_before": prop["fit_before"], "fit_after": prop["fit_after"],
             "оси_сейчас": prop["before_axes"], "оси_после": prop["after_axes"], "цель": prop["mandate_target"],
             "сделки": [f"{'купить' if t['side'] == 'buy' else 'продать'} {t['shortname']} на {t['rub']} ₽" for t in prop["trades"][:8]]}
    try:
        data, m = ai.agent_rationale(facts)
        prop["rationale"] = data.get("text", "")
        return [{**m, "what": "объяснение агента"}]
    except LLMError:
        prop["rationale"] = ""
        return []


# ---------------------------------------------------------------- фронтенд
@app.get("/")
def index():
    return FileResponse(FRONT / "index.html")


@app.get("/v2")
def index_v2():
    """Пошаговый вариант интерфейса: пожелания → бумаги → итог."""
    return FileResponse(FRONT / "v2.html")


app.mount("/static", StaticFiles(directory=FRONT), name="static")


@app.get("/account")
def account_page():
    return FileResponse(FRONT / "account.html")


from .accounts import build_router

app.include_router(build_router(compute, apply_interpret, summary))

from . import community, management
from .video_prototype import router as video_router
from .accounts import loaded, saved, public_record

app.include_router(management.build_router(compute, loaded, saved, public_record))
app.include_router(community.build_router(compute, loaded, public_record))
app.include_router(video_router)


@app.get("/community")
def community_page():
    return FileResponse(FRONT / "community.html")
