"""Isolated paper execution accounts for the local product prototype.

These operations never call a broker or transfer money. The approved mandate,
positions and events of an agent account are separate from the manual account.
"""
import hashlib
import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

from . import account_store as store
from .agent import check_red_lines, propose, simulate_month
from .profile import fold
from .schemas import Holding, State
from .universe import get_universe

AGENTS = {
    "balance": {"id": "balance", "name": "Баланс", "initials": "Б", "role": "Диверсификация и контроль риска", "color": "#b4a1fa"},
    "dividend": {"id": "dividend", "name": "Дивиденд", "initials": "Д", "role": "Денежный поток и качество", "color": "#e5c877"},
    "momentum": {"id": "momentum", "name": "Импульс", "initials": "И", "role": "Рост и изменение трендов", "color": "#8bb8a7"},
}


def policy_key(state):
    p = fold(state)
    data = {"target": p.target, "importance": p.importance, "horizon": p.horizon,
            "red_lines": [r.model_dump() for r in p.red_lines], "themes": [t.model_dump() for t in p.themes]}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def summary(record):
    management = record.get("management") or {"mode": "manual", "account": None}
    account = management.get("account")
    result = {"mode": management.get("mode", "manual"), "account": None, "mandate_changed": False}
    if account:
        result["account"] = {k: v for k, v in account.items() if k not in ("mandate_state", "approved_policy")}
        result["account"]["agent"] = AGENTS.get(account["agent_id"], AGENTS["balance"])
        result["account"]["rules"] = [r.label for r in fold(State.model_validate(account["mandate_state"])).red_lines]
        result["mandate_changed"] = policy_key(State.model_validate(record["state"])) != account["approved_policy"]
    return result


def account_state(record):
    m = record.get("management") or {}
    account = m.get("account")
    if m.get("mode") != "agent" or not account:
        return None
    state = State.model_validate(account["mandate_state"])
    state.amount_rub = account["value"]
    state.executed_value = account["value"]
    state.executed = [Holding.model_validate(h) for h in account["holdings"]]
    return state


def execution_key(record):
    account = (record.get("management") or {}).get("account")
    if (record.get("management") or {}).get("mode") != "agent" or not account:
        return None
    return hashlib.sha256(json.dumps({k: account[k] for k in ("id", "holdings", "value")}, sort_keys=True).encode()).hexdigest()


def configure(record, mode, agent_id, amount, compute):
    m = record.setdefault("management", {"mode": "manual", "account": None})
    if mode == "manual":
        m["mode"] = "manual"
        if m.get("account"):
            m["account"]["status"] = "paused"
            m["account"]["events"].append({"id": uuid4().hex, "at": store.now(), "type": "paused", "text": "Управление возвращено владельцу", "trades": []})
        return
    if agent_id not in AGENTS:
        raise HTTPException(400, "Выберите агента")
    state = State.model_validate(record["state"])
    if m.get("account"):
        account = m["account"]
        # Reusing a mandate never creates or replaces an account or its money.
        if abs(amount - account["initial_amount"]) > 0.01:
            raise HTTPException(400, "Сумма уже выделена этому счёту. Она не меняется при переключении управления.")
        account["agent_id"] = agent_id
        account["status"] = "active"
        account["mandate_state"] = state.model_dump()
        account["approved_policy"] = policy_key(state)
        account["events"].append({"id": uuid4().hex, "at": store.now(), "type": "mandate", "text": "Владелец подтвердил поручение агенту", "trades": []})
    else:
        working = state.model_copy(deep=True)
        working.amount_rub = amount
        working.executed = None
        portfolio, _ = compute(working)
        if portfolio.get("error"):
            raise HTTPException(400, portfolio["error"])
        weights = {h["secid"]: h["weight"] for h in portfolio["holdings"]}
        checks = check_red_lines(get_universe(), fold(working), weights, amount)
        if not all(c["ok"] for c in checks):
            raise HTTPException(400, "Этот состав не проходит ограничения поручения")
        initial = propose(get_universe(), fold(working), portfolio, None, amount)
        account = {"id": "AG-" + uuid4().hex[:8].upper(), "agent_id": agent_id, "status": "active",
                   "initial_amount": amount, "value": amount, "step": 0, "created_at": store.now(),
                   "holdings": [{"secid": h["secid"], "weight": h["weight"]} for h in portfolio["holdings"]],
                   "mandate_state": state.model_dump(), "approved_policy": policy_key(state),
                   "events": [{"id": uuid4().hex, "at": store.now(), "type": "opened", "text": "Отдельный счёт открыт. Агент сформировал портфель по вашему поручению.", "trades": initial["trades"], "checks": checks}]}
        m["account"] = account
    m["mode"] = "agent"


def review(record, compute):
    m = record.get("management") or {}
    account = m.get("account")
    if m.get("mode") != "agent" or not account or account["status"] != "active":
        raise HTTPException(409, "Агент остановлен. Возобновите управление, чтобы запустить обзор.")
    U = get_universe()
    weights, value, period = simulate_month(U, {h["secid"]: h["weight"] for h in account["holdings"]}, account["value"], account["step"])
    state = State.model_validate(account["mandate_state"])
    state.amount_rub = value
    target, _ = compute(state)
    if target.get("error"):
        raise HTTPException(400, target["error"])
    proposal = propose(U, fold(state), target, weights, value)
    checks = proposal["checks_after"]
    executed = proposal["all_ok"] and bool(proposal["trades"])
    account["holdings"] = proposal["after"] if executed else [{"secid": s, "weight": w} for s, w in weights.items()]
    account["value"] = round(value, 2)
    account["step"] += 1
    account["events"].append({"id": uuid4().hex, "at": store.now(), "type": "rebalance" if executed else "review",
                              "text": (f"Агент выполнил {len(proposal['trades'])} сделок в рамках поручения." if executed else
                                       "Изменения не требуются." if proposal["all_ok"] else "Сделки отклонены: нарушаются ограничения поручения."),
                              "period": period, "trades": proposal["trades"] if executed else [], "checks": checks})


class ManagementRequest(BaseModel):
    revision: int = Field(ge=1)
    mode: Literal["manual", "agent"]
    agent_id: str = "balance"
    amount_rub: float = Field(default=250000, ge=10000, le=1e10)


class ActionRequest(BaseModel):
    revision: int = Field(ge=1)
    action: Literal["pause", "resume", "review", "approve_mandate"]


def build_router(compute, loaded, saved, public_record):
    router = APIRouter(prefix="/api/account/portfolios")

    @router.put("/{portfolio_id}/management")
    def set_management(portfolio_id: str, req: ManagementRequest):
        record = loaded(portfolio_id)
        if req.revision != record["revision"]:
            raise HTTPException(409, "Портфель изменился. Обновите страницу.")
        configure(record, req.mode, req.agent_id, req.amount_rub, compute)
        return public_record(saved(record), compute)

    @router.post("/{portfolio_id}/management/actions")
    def action(portfolio_id: str, req: ActionRequest):
        record = loaded(portfolio_id)
        if req.revision != record["revision"]:
            raise HTTPException(409, "Портфель изменился. Обновите страницу.")
        account = (record.get("management") or {}).get("account")
        if not account:
            raise HTTPException(400, "Сначала создайте счёт для агента")
        if req.action == "review":
            review(record, compute)
        elif req.action == "approve_mandate":
            state = State.model_validate(record["state"])
            account["mandate_state"] = state.model_dump()
            account["approved_policy"] = policy_key(state)
            account["events"].append({"id": uuid4().hex, "at": store.now(), "type": "mandate", "text": "Новое поручение подтверждено владельцем", "trades": []})
        else:
            account["status"] = "paused" if req.action == "pause" else "active"
            if req.action == "resume":
                record["management"]["mode"] = "agent"
            account["events"].append({"id": uuid4().hex, "at": store.now(), "type": req.action,
                                      "text": "Агент на паузе" if req.action == "pause" else "Управление агентом возобновлено", "trades": []})
        return public_record(saved(record), compute)

    return router
