"""Community examples and user-published strategy snapshots for the local prototype."""
import json
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import account_store as store, management
from .axes import SECTORS
from .profile import fold
from .schemas import State, Theme
from .universe import get_universe

CATALOG = [
    {"id": "gold-defense", "kind": "portfolio", "title": "Золото и защита", "author": "Защитная часть", "initials": "ЗЧ",
     "description": "Золотодобывающие компании и облигации как дополнение к основному портфелю.",
     "risk": "moderate", "horizon": 5, "sector": "metals_mining", "share": .35, "axes": [6, 5, 5, 7, 7], "tags": ["Золото", "Диверсификация"]},
    {"id": "balanced-start", "kind": "portfolio", "title": "Сбалансированный старт", "author": "Студия стратегий", "initials": "СС",
     "description": "Несколько отраслей, крупные компании и облигации. Отправная точка для собственной стратегии.",
     "risk": "moderate", "horizon": 5, "sector": None, "share": 0, "axes": [5, 5, 6, 7, 8], "tags": ["Баланс", "Первый портфель"]},
    {"id": "dividend-club", "kind": "portfolio", "title": "Дивиденды без спешки", "author": "Дивидендный клуб", "initials": "ДК",
     "description": "Компании с денежным потоком и облигации. Для тех, кто строит дополнительный доход на годы.",
     "risk": "moderate", "horizon": 5, "sector": "oil_gas", "share": .3, "axes": [5, 4, 9, 8, 8], "tags": ["Дивиденды", "ОФЗ"]},
    {"id": "tech-future", "kind": "portfolio", "title": "Технологии завтрашнего дня", "author": "Технологии завтра", "initials": "ТЗ",
     "description": "Российские технологии и компании роста. Длинный горизонт и готовность к заметным колебаниям.",
     "risk": "high", "horizon": 7, "sector": "it_internet", "share": .55, "axes": [9, 8, 2, 3, 6], "tags": ["Рост", "IT"]},
    {"id": "quiet-capital", "kind": "portfolio", "title": "Спокойный капитал", "author": "Капитал по плану", "initials": "КП",
     "description": "ОФЗ и крупные компании. Приоритет — устойчивость и понятные источники дохода.",
     "risk": "low", "horizon": 3, "sector": "gov_bonds", "share": .6, "axes": [3, 3, 7, 9, 8], "tags": ["ОФЗ", "Устойчивость"]},
    {"id": "energy-income", "kind": "portfolio", "title": "Энергия и дивиденды", "author": "Энергия рынка", "initials": "ЭР",
     "description": "Нефтегазовая идея с дивидендами и отдельной защитной частью в облигациях.",
     "risk": "high", "horizon": 5, "sector": "oil_gas", "share": .55, "axes": [6, 5, 8, 5, 8], "tags": ["Нефтегаз", "Дивиденды"]},
    {"id": "agent-balance", "kind": "agent", "title": "Баланс", "portfolio_title": "Сбалансированный старт", "author": "Студия стратегий", "initials": "Б",
     "description": "Следит за долями отраслей и возвращает портфель к вашему профилю. Каждое решение объясняет в журнале.",
     "risk": "moderate", "horizon": 5, "sector": None, "share": 0, "axes": [5, 5, 6, 8, 8], "tags": ["Диверсификация", "Контроль риска"], "agent_id": "balance"},
    {"id": "agent-dividend", "kind": "agent", "title": "Дивиденд", "portfolio_title": "Доход на длинной дистанции", "author": "Дивидендный клуб", "initials": "Д",
     "description": "Ведёт портфель с приоритетом денежного потока, качества и ограничений на концентрацию.",
     "risk": "moderate", "horizon": 5, "sector": "oil_gas", "share": .3, "axes": [4, 4, 9, 8, 8], "tags": ["Денежный поток", "Качество"], "agent_id": "dividend"},
    {"id": "agent-momentum", "kind": "agent", "title": "Импульс", "portfolio_title": "Технологии и рост", "author": "Технологии завтра", "initials": "И",
     "description": "Работает с портфелем роста. Проверяет соответствие трендам и заданным владельцем границам риска.",
     "risk": "high", "horizon": 7, "sector": "it_internet", "share": .5, "axes": [9, 8, 3, 4, 6], "tags": ["Рост", "Тренды"], "agent_id": "momentum"},
]


def blueprint(item):
    if item.get("blueprint"):
        return State.model_validate(item["blueprint"])
    state = State(manual_axes=dict(zip(("growth", "trend", "dividends", "stability", "quality"), item["axes"])), horizon_years=item["horizon"])
    if item.get("sector"):
        matches = [{"secid": s["secid"], "relevance": 1, "why": item["title"]} for s in get_universe().secs if s["sector"] == item["sector"]]
        state.manual_themes = [Theme(id="community_theme", query=SECTORS[item["sector"]], max_share=item["share"], resolved=True, matches=matches)]
    return state


def custom_items():
    with store.connection() as db:
        db.execute("CREATE TABLE IF NOT EXISTS community_listings (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
        return [json.loads(row["data"]) for row in db.execute("SELECT data FROM community_listings ORDER BY rowid DESC")]


def items():
    return custom_items() + CATALOG


def find(item_id):
    item = next((item for item in items() if item["id"] == item_id), None)
    if not item:
        raise HTTPException(404, "Идея не найдена")
    return item


def view(item, compute):
    state = blueprint(item)
    portfolio, _ = compute(state)
    if portfolio.get("error"):
        raise HTTPException(400, portfolio["error"])
    return {k: v for k, v in item.items() if k != "blueprint"} | {
        "target": fold(state).target, "horizon": state.horizon_years,
        "rules": [r.label for r in fold(state).red_lines], "sectors": portfolio["sectors"],
        "holdings": [{k: h[k] for k in ("secid", "shortname", "weight", "sector_ru")} for h in portfolio["holdings"]],
        "history": portfolio["backtest"]["values"], "agent": management.AGENTS.get(item.get("agent_id")),
    }


class UseRequest(BaseModel):
    title: str = Field(default="", max_length=80)
    amount_rub: float = Field(default=250000, ge=10000, le=1e10)
    mode: Literal["manual", "agent"] = "manual"


class PublishRequest(BaseModel):
    portfolio_id: str
    kind: Literal["portfolio", "agent"] = "portfolio"
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)


def build_router(compute, loaded, public_record):
    router = APIRouter(prefix="/api/community")

    @router.get("")
    def list_items():
        return {"items": [view(item, compute) for item in items()]}

    @router.get("/{item_id}")
    def detail(item_id: str):
        return view(find(item_id), compute)

    @router.post("/publish", status_code=201)
    def publish(req: PublishRequest):
        record = loaded(req.portfolio_id)
        state = State.model_validate(record["state"])
        account = (record.get("management") or {}).get("account")
        if req.kind == "agent":
            if (record.get("management") or {}).get("mode") != "agent" or not account:
                raise HTTPException(400, "Сначала поручите портфель агенту")
            state = State.model_validate(account["mandate_state"])
        # Explicit public snapshot: no messages, source texts, account IDs, balances,
        # executed positions, simulation logs or private record ID.
        p = fold(state)
        public_lines = []
        for i, line in enumerate(p.red_lines):
            label = {"no_margin": "Без заёмных денег", "max_position": f"Одна бумага: до {(line.value or 0):.0%}",
                     "exclude_sector": "Без отрасли: " + SECTORS.get(line.sector, ""), "exclude_security": "Исключена бумага: " + (line.secid or ""),
                     "max_sector_share": f"{SECTORS.get(line.sector, '')}: до {(line.value or 0):.0%}",
                     "max_drawdown_rub": "Предел просадки: " + str(round(line.value or 0)) + " ₽"}[line.kind]
            public_lines.append(line.model_copy(update={"id": "public_rule_" + str(i), "label": label, "source": "правила стратегии"}))
        public_themes = [t.model_copy(update={"id": "public_theme_" + str(i), "query": "Тематическая часть стратегии", "source": "тема стратегии", "resolved": True,
                                            "matches": [{"secid": m["secid"], "relevance": m.get("relevance", 1), "why": "Тема стратегии"} for m in t.matches]})
                         for i, t in enumerate(p.themes) if t.matches]
        public_state = State(manual_axes=p.target, horizon_years=state.horizon_years,
                             disabled_defaults=["def_maxpos", "def_nomargin"],
                             manual_red_lines=public_lines, manual_themes=public_themes)
        title = req.title.strip()
        if not title:
            raise HTTPException(400, "Введите название")
        item = {"id": "published-" + uuid4().hex, "kind": req.kind, "title": title,
                "portfolio_title": title if req.kind == "agent" else None, "author": "Мой профиль", "initials": "Я",
                "description": req.description.strip(), "risk": "high" if p.target["stability"] < 5 else "low" if p.target["stability"] >= 9 else "moderate",
                "horizon": state.horizon_years, "tags": ["Авторская стратегия"], "blueprint": public_state.model_dump(),
                "created_at": store.now(), "agent_id": account["agent_id"] if req.kind == "agent" else None}
        with store.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS community_listings (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("INSERT INTO community_listings VALUES (?, ?)", (item["id"], json.dumps(item, ensure_ascii=False)))
        return view(item, compute)

    @router.post("/{item_id}/use", status_code=201)
    def use(item_id: str, req: UseRequest):
        item = find(item_id)
        state = blueprint(item)
        state.amount_rub = req.amount_rub
        state.executed = None
        state.executed_value = None
        title = req.title.strip() or item.get("portfolio_title") or item["title"]
        text = f"За основу взята стратегия «{item['title']}». {item['description']}"
        source = {"id": uuid4().hex, "kind": "text", "title": item["title"], "url": "/community?item=" + item_id, "text": text, "at": store.now()}
        data = {"title": title, "description": item["description"], "strategy_origin": "external", "source_kind": "text",
                "source_url": source["url"], "source_text": text, "is_example": False, "state": state.model_dump(),
                "sources": [source], "plans": [], "editor_chat": [{"role": "agent", "text": text}],
                "messages": [{"id": uuid4().hex, "role": "assistant", "text": text, "at": store.now()}],
                "community_origin": {"id": item["id"], "kind": item["kind"], "title": item["title"]}}
        if req.mode == "agent":
            management.configure(data, "agent", item.get("agent_id") or "balance", req.amount_rub, compute)
        return public_record(store.create(data), compute)

    return router
