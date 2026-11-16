"""Cabinet API: named portfolios, independent profiles and persistent research chats."""
import hashlib
import json
import sqlite3
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import account_store as store, config, research, management
from .agent import check_red_lines, propose
from .axes import AXES, SECTORS
from .llm import LLMError
from .optimizer import backtest, portfolio_axes
from .profile import all_red_lines, fold
from .schemas import Holding, RedLine, State, Theme, Wish
from .sources import read_article
from .universe import get_universe


class CreatePortfolio(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    text: str = Field(default="", max_length=16000)
    strategy_origin: Literal["own", "external"] | None = None
    source_kind: Literal["idea", "video", "article", "text"] = "idea"
    source_url: str = Field(default="", max_length=2000)
    source_file_name: str = Field(default="", max_length=260)
    source_analysis_mode: Literal["provided", "prototype"] = "provided"
    amount_rub: float = Field(default=500_000, ge=10_000, le=1e10)
    horizon_years: int = Field(default=5, ge=1, le=30)


class SavePortfolio(BaseModel):
    revision: int = Field(ge=1)
    state: State
    editor_chat: list[dict] = Field(default_factory=list, max_length=500)
    title: str | None = Field(default=None, min_length=1, max_length=80)


class ChatRequest(BaseModel):
    text: str = Field(default="", max_length=8000)
    article_text: str = Field(default="", max_length=16000)
    source_url: str = Field(default="", max_length=2000)
    intent: Literal["question", "idea"] = "question"
    source_kind: Literal["video", "article", "text"] = "article"
    source_title: str = Field(default="", max_length=160)
    source_file_name: str = Field(default="", max_length=260)
    source_analysis_mode: Literal["provided", "prototype"] = "provided"


def origin(record):
    return record.get("strategy_origin", "external" if record["source_kind"] != "idea" else "own")


def plan_for(record, state, portfolio, current, candidate, compute, title, source_id=None):
    working = candidate.model_copy(deep=True)
    working.amount_rub = current["amount"] if current else state.amount_rub
    after, _ = compute(working)
    if after.get("error"):
        return None
    weights = {h["secid"]: h["weight"] for h in after["holdings"]}
    checks = check_red_lines(get_universe(), fold(working), weights, working.amount_rub)
    original_checks = check_red_lines(get_universe(), fold(state), weights, working.amount_rub)
    if not all(c["ok"] for c in checks + original_checks):
        return None
    before = current["holdings"] if current else portfolio["holdings"]
    proposal = propose(get_universe(), fold(working), after, {h["secid"]: h["weight"] for h in before}, working.amount_rub)
    plan = {"id": uuid4().hex, "title": title, "status": "pending", "source_id": source_id,
            "base_fingerprint": fingerprint(record["state"]), "account_key": management.execution_key(record), "state": candidate.model_dump(),
            "before": current["sectors"] if current else portfolio["sectors"], "after": after["sectors"],
            "before_axes": current["axes"] if current else portfolio["achieved"],
            "after_axes": after["achieved"], "checks": checks, "proposal": proposal}
    record["plans"].append(plan)
    return plan


def fingerprint(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def loaded(portfolio_id):
    record = store.get(portfolio_id)
    if not record:
        raise HTTPException(404, "Портфель не найден")
    return record


def saved(record):
    result = store.update(record, record["revision"])
    if not result:
        raise HTTPException(409, "Портфель изменился в другой вкладке. Обновите страницу перед продолжением.")
    return result


def exposure(state):
    U = get_universe()
    holdings = state.executed or []
    idx = [U.by_id[h.secid] for h in holdings if h.secid in U.by_id and h.weight > 0]
    weights = np.array([h.weight for h in holdings if h.secid in U.by_id and h.weight > 0])
    if not len(idx) or weights.sum() <= 0:
        return None
    weights /= weights.sum()
    amount = state.executed_value if state.executed_value is not None else state.amount_rub
    sectors, rows = {}, []
    for i, weight in zip(idx, weights):
        sec = U.secs[i]
        sectors[sec["sector"]] = sectors.get(sec["sector"], 0) + float(weight)
        rows.append({**{k: sec.get(k) for k in ("secid", "shortname", "sector", "price", "lot", "div_yield", "kind")},
                     "weight": round(float(weight), 4), "rub": round(amount * weight), "sector_ru": SECTORS.get(sec["sector"], "Прочее")})
    bt = backtest(U, idx, weights, amount)
    return {"holdings": sorted(rows, key=lambda r: -r["weight"]), "amount": amount,
            "sectors": sorted([{"sector": k, "name": SECTORS.get(k, k), "weight": round(v, 4)} for k, v in sectors.items()], key=lambda r: -r["weight"]),
            "axes": dict(zip(AXES, portfolio_axes(U, idx, weights).round(2).tolist())),
            "history": [round(v) for v in bt["values"][::4]], "ann_return": round(bt["ann_return"], 4)}


def public_record(record, compute):
    state = State.model_validate(record["state"])
    delegated = management.account_state(record)
    working = state.model_copy(deep=True)
    if delegated:
        working.amount_rub = delegated.amount_rub
    portfolio, _ = compute(working)
    current = exposure(delegated or state)
    return {**record, "strategy_origin": origin(record), "sources": record.get("sources", []),
            "portfolio": portfolio, "current": current, "management": management.summary(record), "mock": config.MOCK}


def seed_examples(compute):
    if store.list_all():
        return
    U = get_universe()
    for pid, title, desc, kind, amount, axes, theme_sector in [
        ("example-oil", "Нефтегаз и дивиденды", "Дивидендная идея с фокусом на нефтегаз и защитной частью в ОФЗ.", "idea", 650_000,
         {"growth": 6, "trend": 5, "dividends": 8, "stability": 6, "quality": 8}, "oil_gas"),
        ("example-video", "Смелая идея из видео", "Рост и российские технологии. Высокий риск, небольшой отдельный бюджет.", "video", 250_000,
         {"growth": 9, "trend": 8, "dividends": 2, "stability": 3, "quality": 5}, "it_internet"),
    ]:
        idea = ("Хочу дивиденды от нефтегазовых компаний. Часть держу в ОФЗ. Без заёмных денег. Горизонт 5 лет."
                if kind == "idea" else "Пример идеи из ролика: российские IT-компании, агрессивный рост, готовность к сильным колебаниям. Без плеча. Горизонт 5 лет.")
        state = State(amount_rub=amount, manual_axes=axes, messages=[idea])
        state.wishes = [Wish(id="seed-wish", span=idea, label="Дивиденды и нефтегаз" if kind == "idea" else "Рост и высокий риск", type="axis")]
        matching = [s["secid"] for s in U.secs if s["sector"] == theme_sector]
        state.manual_themes = [Theme(id="seed-theme", query=SECTORS[theme_sector], max_share=0.65, resolved=True,
                                    matches=[{"secid": s, "relevance": 1, "why": "Тема примера"} for s in matching])]
        # Illustrative virtual holdings, with all actual tickers from the loaded universe.
        first = matching[:6]
        other = [s["secid"] for s in U.secs if s["sector"] == "gov_bonds"][:4]
        chosen = first + other
        if len(chosen) >= 9:
            state.executed = [Holding(secid=s, weight=1 / len(chosen)) for s in chosen]
            state.executed_value = amount
        else:
            p, _ = compute(state)
            if not p.get("error"):
                state.executed = [Holding(secid=h["secid"], weight=h["weight"]) for h in p["holdings"]]
                state.executed_value = amount
        state.agent_log = [{"at": "Пример", "type": "initial", "text": "Создан учебный состав. Реальные покупки не совершались."}]
        welcome = ("Сохранил дивидендную идею: нефтегаз, защитная часть в ОФЗ и без заёмных денег. Можем обсуждать новости в контексте именно этого портфеля."
                   if kind == "idea" else "Сохранил идею из видео: российские технологии, рост и готовность к колебаниям. Можем адаптировать её под ваши цели и ограничения.")
        try:
            store.create({"title": title, "description": desc, "source_kind": kind, "source_url": "", "source_text": idea,
                          "is_example": True, "state": state.model_dump(),
                          "editor_chat": [{"role": "user", "text": idea}, {"role": "agent", "text": welcome, "ids": ["seed-wish"]}],
                          "messages": [{"id": uuid4().hex, "role": "user", "text": idea, "at": store.now()},
                                       {"id": uuid4().hex, "role": "assistant", "text": welcome, "at": store.now()}], "plans": []}, pid)
        except sqlite3.IntegrityError:
            pass  # Another request initialized these same examples.


def build_router(compute, apply_interpret, summary):
    router = APIRouter(prefix="/api/account")

    @router.get("/portfolios")
    def list_portfolios():
        seed_examples(compute)
        records = []
        for record in store.list_all():
            state = State.model_validate(record["state"])
            current = exposure(management.account_state(record) or state)
            records.append({k: record[k] for k in ("id", "title", "description", "source_kind", "source_url", "is_example", "updated_at", "revision")} |
                           {"amount_rub": current["amount"] if current else state.amount_rub, "horizon_years": state.horizon_years, "target": fold(state).target,
                            "strategy_origin": origin(record), "current": current,
                            "message_count": len(record["messages"]), "autonomy": state.autonomy, "management": management.summary(record)})
        return {"portfolios": records, "mock": config.MOCK, "local_account": True}

    @router.post("/portfolios", status_code=201)
    def create_portfolio(req: CreatePortfolio):
        title = req.title.strip()
        if not title:
            raise HTTPException(400, "Введите название портфеля")
        if req.source_url:
            parsed = urlsplit(req.source_url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                raise HTTPException(400, "Проверьте ссылку на источник")
        strategy_origin = req.strategy_origin or ("own" if req.source_kind == "idea" else "external")
        kind = "idea" if strategy_origin == "own" else (req.source_kind if req.source_kind != "idea" else "text")
        text = req.text.strip()
        if kind == "article" and req.source_url and not text:
            article = read_article(req.source_url)
            if article["status"] != "read":
                raise HTTPException(400, article["notice"])
            text = article["text"]
        if kind == "video" and not text:
            raise HTTPException(400, "Добавьте текст или расшифровку видео: по одной ссылке его содержание пока недоступно.")
        if strategy_origin == "external" and not text:
            raise HTTPException(400, "Добавьте текст идеи или ссылку на статью")
        state = State(amount_rub=req.amount_rub, horizon_years=req.horizon_years)
        editor_chat, messages = [], []
        if text:
            from . import ai
            try:
                data, _ = ai.interpret(text, summary(state))
            except LLMError as exc:
                raise HTTPException(502, str(exc)) from exc
            ids = apply_interpret(state, text, data)
            editor_chat = [{"role": "user", "text": text}, {"role": "agent", "text": data.get("reply", ""), "ids": ids}]
            messages = [{"id": uuid4().hex, "role": "user", "text": text, "at": store.now()},
                        {"id": uuid4().hex, "role": "assistant", "text": data.get("reply", "Сохранил исходную идею."), "at": store.now()}]
        sources = [{"id": uuid4().hex, "kind": kind, "title": title, "url": req.source_url, "text": text,
                    "file_name": req.source_file_name, "analysis_mode": req.source_analysis_mode, "at": store.now()}] if strategy_origin == "external" else []
        record = store.create({"title": title, "description": req.description.strip(), "strategy_origin": strategy_origin, "source_kind": kind,
                               "source_url": req.source_url, "source_text": text, "is_example": False, "sources": sources,
                               "state": state.model_dump(), "editor_chat": editor_chat, "messages": messages, "plans": []})
        return record

    @router.get("/portfolios/{portfolio_id}")
    def get_portfolio(portfolio_id: str):
        return public_record(loaded(portfolio_id), compute)

    @router.put("/portfolios/{portfolio_id}")
    def save_portfolio(portfolio_id: str, req: SavePortfolio):
        record = loaded(portfolio_id)
        if req.revision != record["revision"]:
            raise HTTPException(409, "Портфель изменился в другой вкладке. Обновите страницу.")
        record["state"] = req.state.model_dump()
        record["editor_chat"] = [m for m in req.editor_chat if m.get("role") != "wait"]
        if req.title is not None:
            if not req.title.strip():
                raise HTTPException(400, "Название не может быть пустым")
            record["title"] = req.title.strip()
        return public_record(saved(record), compute)

    @router.post("/portfolios/{portfolio_id}/chat")
    def chat(portfolio_id: str, req: ChatRequest):
        record = loaded(portfolio_id)
        if not (req.text.strip() or req.article_text.strip() or req.source_url.strip()):
            raise HTTPException(400, "Напишите вопрос или добавьте новость")
        if req.source_url:
            try:
                parsed = urlsplit(req.source_url)
                valid = parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password
            except ValueError:
                valid = False
            if not valid:
                raise HTTPException(400, "Проверьте ссылку на источник")
        attachment = None
        if req.article_text.strip():
            attachment = {"status": "read", "text": req.article_text.strip(), "url": req.source_url,
                          "notice": "Текст предоставлен вами; достоверность отдельно не проверена."}
        elif req.source_url:
            attachment = read_article(req.source_url)
        source = None
        if req.intent == "idea":
            if not attachment or attachment["status"] != "read":
                raise HTTPException(400, (attachment or {}).get("notice", "Добавьте текст идеи или ссылку на статью"))
            source = {"id": uuid4().hex, "kind": req.source_kind,
                      "title": req.source_title.strip() or {"video": "Идея из видео", "article": "Идея из статьи", "text": "Новая идея"}[req.source_kind],
                      "url": req.source_url, "text": attachment["text"], "file_name": req.source_file_name,
                      "analysis_mode": req.source_analysis_mode, "at": store.now()}
            attachment.update({"kind": source["kind"], "title": source["title"], "source_id": source["id"]})
        state = State.model_validate(record["state"])
        delegated = management.account_state(record)
        working = state.model_copy(deep=True)
        if delegated:
            working.amount_rub = delegated.amount_rub
        p, _ = compute(working)
        if p.get("error"):
            raise HTTPException(400, "Сначала исправьте ограничения портфеля: " + p["error"])
        current = exposure(delegated or state)
        context = {"title": record["title"], "source_text": record["source_text"], "profile_messages": state.messages,
                   "editor_chat": record["editor_chat"][-40:], "sources": record.get("sources", []), "target": p["target"], "amount_rub": working.amount_rub,
                   "management": management.summary(record),
                   "previous_scenarios": [{k: plan.get(k) for k in ("title", "status", "source_id", "before", "after")}
                                          for plan in record["plans"][-20:]],
                   "horizon_years": state.horizon_years, "wishes": [w.label for w in state.wishes if w.status == "accepted"],
                   "red_lines": [l.model_dump() for l in all_red_lines(state) if l.active],
                   "holdings": current["holdings"] if current else p["holdings"],
                   "sectors": current["sectors"] if current else p["sectors"]}
        question = req.text.strip() or ("Как адаптировать мой портфель на основе этой идеи?" if source else "Как эта новость влияет на мой портфель?")
        try:
            answer, meta = (research.adapt_idea(question, context, record["messages"], source) if source
                            else research.discuss(question, context, record["messages"], attachment))
        except LLMError as exc:
            raise HTTPException(502, str(exc)) from exc
        plan = None
        sectors = context["sectors"]
        top = max(sectors, key=lambda s: s["weight"], default=None)
        candidate = state.model_copy(deep=True)
        if (answer.get("scenario") == "diversify" or (source and answer.get("reduce_concentration"))) and top and top["weight"] > 0.3:
            line_id = "research_concentration_" + top["sector"]
            cap = min([0.3] + [l.value for l in all_red_lines(candidate)
                              if l.active and l.kind == "max_sector_share" and l.sector == top["sector"] and l.value is not None])
            candidate.manual_red_lines = [l for l in candidate.manual_red_lines if l.id != line_id]
            candidate.manual_red_lines.append(RedLine(id=line_id, kind="max_sector_share", sector=top["sector"],
                                                       value=cap, label=f"{top['name']}: не больше {cap:.0%}", source="сценарий из аналитического чата"))
            # External ideas do not rewrite the investor's existing goals.
            if not source:
                candidate.manual_axes["stability"] = min(10, fold(state).target["stability"] + 1.5)
        if source:
            from .optimizer import constraints_from
            U = get_universe()
            allowed, _, _, _ = constraints_from(U, fold(state))
            requested = [s for s in answer.get("sectors", []) if s in SECTORS]
            matching = [{"secid": sec["secid"], "relevance": 1, "why": source["title"]}
                        for i, sec in enumerate(U.secs) if allowed[i] and sec["sector"] in requested]
            blocked = [sector for sector in requested if not any(allowed[i] and sec["sector"] == sector for i, sec in enumerate(U.secs))]
            if matching:
                candidate.manual_themes.append(Theme(id="idea_" + source["id"], query=source["title"],
                                                     max_share=0.1, source="чужая идея", resolved=True, matches=matching))
            if blocked:
                answer["answer"] += "\n\nС учётом текущих ограничений или доступных бумаг не добавляю: " + ", ".join(SECTORS[s] for s in blocked) + "."
            record.setdefault("sources", []).append(source)
        if candidate.model_dump() != state.model_dump():
            plan = plan_for(record, state, p, current, candidate, compute,
                            ("Идея: " + source["title"]) if source else "Меньше концентрации, больше устойчивости",
                            source["id"] if source else None)
        if source:
            if plan:
                answer["answer"] += "\n\nНиже — сравнение с текущим составом."
                if matching:
                    answer["answer"] += " Для добавленной идеи задан лимит 10% портфеля."
            else:
                answer["answer"] += "\n\nПока сохраняю материал без изменения плана. Уточните, какую часть идеи вы хотите использовать."
        user = {"id": uuid4().hex, "role": "user", "text": question, "at": store.now(), "attachment": attachment, "intent": req.intent}
        assistant = {"id": uuid4().hex, "role": "assistant", "text": answer.get("answer", ""), "title": answer.get("title", ""),
                     "watchpoints": answer.get("watchpoints", [])[:3], "at": store.now(), "plan_id": plan["id"] if plan else None,
                     "mode": "rules" if config.MOCK else "llm"}
        record["messages"] += [user, assistant]
        result = saved(record)
        return {"record": public_record(result, compute), "plan": plan, "llm": meta}

    @router.post("/portfolios/{portfolio_id}/plans/{plan_id}/apply")
    def apply_plan(portfolio_id: str, plan_id: str):
        record = loaded(portfolio_id)
        plan = next((p for p in record["plans"] if p["id"] == plan_id), None)
        if not plan or plan["status"] != "pending":
            raise HTTPException(409, "Этот сценарий уже применён или не найден")
        if fingerprint(record["state"]) != plan["base_fingerprint"]:
            raise HTTPException(409, "Профиль уже изменился. Запросите новый расчёт в чате.")
        if plan.get("account_key") != management.execution_key(record):
            raise HTTPException(409, "Состав или счёт уже изменился. Запросите новый расчёт.")
        candidate = State.model_validate(plan["state"])
        working = candidate.model_copy(deep=True)
        delegated = management.account_state(record)
        if delegated:
            working.amount_rub = delegated.amount_rub
        p, _ = compute(working)
        if p.get("error") or not all(c["ok"] for c in check_red_lines(get_universe(), fold(working), {h["secid"]: h["weight"] for h in p.get("holdings", [])}, working.amount_rub)):
            raise HTTPException(409, "Сценарий больше не проходит ограничения. Пересчитайте его.")
        record["state"] = candidate.model_dump()
        plan["status"] = "applied"
        record["messages"].append({"id": uuid4().hex, "role": "assistant", "text": "План обновлён. Чтобы изменить текущий состав, отдельно подтвердите ребалансировку.", "at": store.now()})
        return public_record(saved(record), compute)

    return router
