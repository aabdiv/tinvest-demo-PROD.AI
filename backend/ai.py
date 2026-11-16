"""Все обращения к LLM: промпты, JSON-схемы и тестовая замена на правилах (MOCK)."""
import json
import re
import time

from . import config
from .axes import AXES, AXIS_RU, SECTORS
from .llm import structured

RL_KINDS = ["none", "exclude_sector", "exclude_security", "max_position", "max_sector_share",
            "max_drawdown_rub", "no_margin"]
SECTOR_ENUM = ["none"] + list(SECTORS.keys())


def _obj(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(props.keys()), "properties": props}


S = {"type": "string"}
N = {"type": "number"}
I = {"type": "integer"}

WISH_ITEM = _obj({
    "span": S, "label": S,
    "type": {"type": "string", "enum": ["axis", "red_line", "theme", "param", "fear", "other"]},
    **{a: I for a in AXES},
    "rl_kind": {"type": "string", "enum": RL_KINDS},
    "rl_sector": {"type": "string", "enum": SECTOR_ENUM},
    "rl_secid": S, "rl_value": N,
    "theme_query": S, "theme_max_share": N,
    "horizon_years": I, "amount_rub": N, "confidence": N,
})
INTERPRET_SCHEMA = _obj({
    "wishes": {"type": "array", "items": WISH_ITEM},
    "contradictions": {"type": "array", "items": _obj({"text": S, "option_a": S, "option_b": S})},
    "reply": S,
})
THEME_SCHEMA = _obj({"matches": {"type": "array", "items": _obj({"secid": S, "relevance": N, "why": S})}})
TEXT_SCHEMA = _obj({"text": S})
MANDATE_SCHEMA = _obj({"mandate": S})
REDLINE_SCHEMA = _obj({"rl_kind": {"type": "string", "enum": RL_KINDS},
                       "rl_sector": {"type": "string", "enum": SECTOR_ENUM}, "rl_secid": S, "rl_value": N, "label": S})
CARDS_SCHEMA = _obj({"cards": {"type": "array", "items": _obj({
    "secid": S, "sector": {"type": "string", "enum": list(SECTORS.keys())}, "description": S,
    "tags": {"type": "array", "items": S}})}})

SECTOR_LIST = "\n".join(f"- {k}: {v}" for k, v in SECTORS.items())
AXES_TEXT = """Оси профиля (шкала 0–10, нейтрально 5):
- growth (Рост): насколько человек хочет роста капитала;
- trend (Тренд): готовность покупать то, что сейчас растёт;
- dividends (Дивиденды): важность регулярного денежного потока (дивиденды, купоны);
- stability (Устойчивость): желание спокойного портфеля с небольшими колебаниями;
- quality (Качество): предпочтение крупных надёжных компаний."""

INTERPRET_SYSTEM = f"""Ты — модуль разбора пожеланий инвестора для ИИ-агента брокера. Человек пишет своими словами,
ты превращаешь текст в список отдельных пожеланий строго по JSON-схеме. Не давай советов и не выдумывай факты.

{AXES_TEXT}

Эффект на ось — целое число от -3 до 3 (1 — слегка, 2 — заметно, 3 — сильно; знак — больше или меньше этого свойства).

Отрасли (ключи для rl_sector):
{SECTOR_LIST}

Правила:
1. Разбей текст на атомарные пожелания. span — короткая точная цитата из текста.
2. label — текст чипа до 30 символов: «Дивиденды ↑», «Горизонт 5 лет», «Без нефти и газа», «Тема: российский IT».
3. type=axis — пожелание про свойства портфеля (только эффекты на оси).
4. type=red_line — явный запрет или лимит («не хочу», «без», «не больше»). rl_kind:
   exclude_sector (rl_sector), exclude_security (rl_secid = тикер), max_position (доля одной бумаги, rl_value дробью: 10% → 0.1),
   max_sector_share (rl_sector и доля), max_drawdown_rub (допустимая временная просадка в рублях), no_margin.
5. type=theme — идея, отрасль или тренд, в который человек верит. theme_query — формулировка для поиска бумаг,
   theme_max_share — доля портфеля 0.05–0.3 (обычно 0.1; если человек осторожен — 0.05).
6. type=fear — страх (обвал, кризис, девальвация, «как в 2022», «не потерять»): эффект stability +2. Если названа сумма
   или доля допустимых потерь, заполни в ЭТОМ ЖЕ пожелании rl_kind=max_drawdown_rub и rl_value в рублях
   (долю пересчитай от суммы). Не создавай второе пожелание с тем же смыслом.
7. type=param — горизонт в годах (horizon_years) и сумма в рублях (amount_rub). «Из 600 тысяч», «600к», «полмиллиона» —
   это сумма: amount_rub=600000 и т.п. Сумму и горизонт оформляй отдельными пожеланиями.
8. Неиспользуемые поля: 0 для чисел, "" для строк, "none" для перечислений.
9. contradictions — ОБЯЗАТЕЛЬНО проверь каждую пару пожеланий между собой и с текущим профилем. Типичные противоречия:
   - приоритет дивидендов или спокойствия и ставка на быстрорастущие отрасли (IT, технологии, биотех), которые
     обычно платят мало дивидендов и сильно колеблются;
   - «максимальная доходность» и «никакого риска» / «не потерять»;
   - короткий горизонт (до 3 лет) и агрессивный рост;
   - запрет отрасли и тема из той же отрасли.
   Пример: «Хочу стабильные дивиденды. Верю в российский IT» → contradictions: [{{"text": "IT-компании редко платят
   большие дивиденды и сильнее колеблются. Как поступим?", "option_a": "Небольшая доля IT", "option_b": "Без IT"}}].
   text — одно-два коротких предложения; option_a и option_b — варианты решения до 30 символов.
   Если противоречий нет — пустой массив.
12. Не дублируй пожелания с одинаковым смыслом.
10. Если текст начинается с «Выбираю:», это решение противоречия: преврати выбор в пожелания (например, тема с меньшей долей).
11. reply — одно короткое предложение о том, что ты понял."""


def _ctx(profile_summary: dict) -> str:
    return json.dumps(profile_summary, ensure_ascii=False)


# ---------------------------------------------------------------- публичные функции
def interpret(text: str, profile_summary: dict) -> tuple[dict, dict]:
    if config.MOCK:
        return mock_interpret(text, profile_summary)
    user = f"Текущий профиль: {_ctx(profile_summary)}\n\nНовое сообщение человека:\n{text}"
    return structured("fast", INTERPRET_SYSTEM, user, "interpret", INTERPRET_SCHEMA, max_tokens=1800)


def resolve_theme(query: str, cards: list[str]) -> tuple[dict, dict]:
    if config.MOCK:
        return mock_theme(query, cards)
    system = ("Ты — агент-поисковик по бумагам Мосбиржи. По теме инвестора выбери из списка до 8 подходящих бумаг. "
              "relevance от 0 до 1, why — до 12 слов, почему бумага подходит. Используй только тикеры из списка.")
    user = f"Тема: {query}\n\nБумаги (тикер | название | отрасль | описание | теги):\n" + "\n".join(cards)
    return structured("fast", system, user, "theme_matches", THEME_SCHEMA, max_tokens=900)


def write_mandate(facts: dict) -> tuple[dict, dict]:
    if config.MOCK:
        return mock_mandate(facts)
    system = ("Ты пишешь мандат ИИ-агента, который управляет портфелем клиента. 2–3 предложения, не больше 55 слов, "
              "простым языком, без жаргона и англицизмов. Включи: характер портфеля и горизонт, на чём он держится "
              "(главные отрасли и доли), допустимую просадку в рублях, если она задана, и главные запреты. "
              "Не обещай доходность. Пиши от третьего лица о портфеле, не о человеке.")
    return structured("fast", system, json.dumps(facts, ensure_ascii=False), "mandate", MANDATE_SCHEMA, max_tokens=400)


def explain_security(facts: dict) -> tuple[dict, dict]:
    if config.MOCK:
        return mock_explain(facts)
    system = ("Объясни инвестору в 2 коротких предложениях, почему агент включил (или не включил) эту бумагу в портфель "
              "и где она сильнее всего расходится с его профилем. Простой язык, без обещаний доходности.")
    return structured("fast", system, json.dumps(facts, ensure_ascii=False), "explain", TEXT_SCHEMA, max_tokens=300)


def parse_red_line(text: str) -> tuple[dict, dict]:
    if config.MOCK:
        return mock_redline(text)
    system = ("Преврати запрет инвестора в одну красную линию по схеме. rl_kind: exclude_sector, exclude_security "
              "(rl_secid — тикер), max_position (доля дробью), max_sector_share (rl_sector и доля), max_drawdown_rub "
              "(рубли), no_margin; если это не запрет — none. label — до 35 символов. Отрасли:\n" + SECTOR_LIST +
              "\nНеиспользуемые поля: 0, \"\", \"none\".")
    return structured("fast", system, text, "red_line", REDLINE_SCHEMA, max_tokens=200)


def agent_rationale(facts: dict) -> tuple[dict, dict]:
    if config.MOCK:
        return mock_rationale(facts)
    system = ("Ты — ИИ-агент, который управляет портфелем по мандату. Объясни клиенту в 1–2 коротких предложениях, "
              "почему ты предлагаешь эти сделки: что сместилось относительно мандата и что сделки исправят. Простой язык.")
    return structured("fast", system, json.dumps(facts, ensure_ascii=False), "rationale", TEXT_SCHEMA, max_tokens=250)


def build_cards(batch: list[dict]) -> list[dict]:
    system = ("Ты размечаешь бумаги Московской биржи для базы данных. Для каждой бумаги дай отрасль из перечня, "
              "одно короткое предложение о бизнесе компании (до 15 слов) и 3–5 тегов для тематического поиска "
              "(например: «дивиденды», «госкомпания», «экспорт», «импортозамещение», «золото»). Если не уверен — "
              "пиши осторожно и общо, не выдумывай цифры. Отрасли:\n" + SECTOR_LIST)
    user = "\n".join(f"{b['secid']} | {b['name']} | {'облигация' if b['kind'] == 'bond' else 'акция'}" for b in batch)
    data, _ = structured("smart", system, user, "cards", CARDS_SCHEMA, max_tokens=4000)
    return data.get("cards", [])


# ---------------------------------------------------------------- тестовый режим на правилах
def _meta(name: str, t0: float) -> dict:
    return {"model": "mock-rules", "ms": int((time.time() - t0) * 1000) + 5, "mode": "mock", "provider": None, "tier": "mock"}


def _blank(span: str, label: str, typ: str, **kw) -> dict:
    w = {"span": span, "label": label, "type": typ, **{a: 0 for a in AXES}, "rl_kind": "none", "rl_sector": "none",
         "rl_secid": "", "rl_value": 0, "theme_query": "", "theme_max_share": 0, "horizon_years": 0,
         "amount_rub": 0, "confidence": 0.7}
    w.update(kw)
    return w


SECTOR_WORDS = {"oil_gas": ["нефт", "газ"], "banks_finance": ["банк"], "it_internet": ["it", "айти", "технолог"],
                "metals_mining": ["металл", "золот"], "real_estate": ["девелоп", "застройщ"],
                "utilities": ["энергет"], "telecom": ["телеком", "связ"]}


def mock_interpret(text: str, profile: dict) -> tuple[dict, dict]:
    t0 = time.time()
    low = text.lower()
    wishes, contr = [], []
    if low.startswith("выбираю:"):
        if "небольш" in low or "мал" in low:
            wishes.append(_blank(text, "Тема: IT, малая доля", "theme", theme_query="российский IT", theme_max_share=0.05))
        elif "без" in low:
            wishes.append(_blank(text, "Без IT", "red_line", rl_kind="exclude_sector", rl_sector="it_internet"))
        return {"wishes": wishes, "contradictions": [], "reply": "Принял выбор."}, _meta("interpret", t0)
    for sent in [s.strip() for s in re.split(r"[.!?;\n]+", text) if s.strip()]:
        s = sent.lower()
        neg = any(n in s for n in ["не хочу", "без ", "не надо", "не нужн", "исключ"])
        hit = False
        if neg:
            for sec, words in SECTOR_WORDS.items():
                if any(wd in s for wd in words):
                    wishes.append(_blank(sent, f"Без: {SECTORS[sec].lower()}", "red_line", rl_kind="exclude_sector", rl_sector=sec))
                    hit = True
        if not neg and ("верю" in s or "интерес" in s or "нравит" in s):
            for sec, words in SECTOR_WORDS.items():
                if any(wd in s for wd in words):
                    wishes.append(_blank(sent, f"Тема: {SECTORS[sec]}", "theme", theme_query=SECTORS[sec], theme_max_share=0.1))
                    hit = True
        if "дивиден" in s or "пассивн" in s or "доп" in s and "доход" in s:
            wishes.append(_blank(sent, "Дивиденды ↑", "axis", dividends=2)); hit = True
        if any(k in s for k in ["спокой", "надёж", "надеж", "безопас", "стабил", "консерв"]):
            wishes.append(_blank(sent, "Устойчивость ↑", "axis", stability=2)); hit = True
        if any(k in s for k in ["рост", "агрессив", "максимальн"]) and not neg:
            wishes.append(_blank(sent, "Рост ↑", "axis", growth=2, stability=-1)); hit = True
        if any(k in s for k in ["крупн", "голуб", "качеств"]):
            wishes.append(_blank(sent, "Качество ↑", "axis", quality=2)); hit = True
        if any(k in s for k in ["боюсь", "страш", "2022", "кризис", "обвал"]):
            amount = profile.get("amount_rub", 500000)
            wishes.append(_blank(sent, "Страх просадки → устойчивость", "fear", stability=2))
            wishes.append(_blank(sent, f"Просадка не глубже −{int(amount * 0.18 / 1000)} тыс. ₽", "red_line",
                                 rl_kind="max_drawdown_rub", rl_value=round(amount * 0.18, -3)))
            hit = True
        m = re.search(r"\b(\d{1,2})\s*(год|лет)", s)
        if m:
            wishes.append(_blank(sent, f"Горизонт {m.group(1)} лет", "param", horizon_years=int(m.group(1)))); hit = True
        m = re.search(r"(\d[\d\s]*)\s*(тыс|руб|₽)", s)
        if m:
            v = float(m.group(1).replace(" ", "")) * (1000 if "тыс" in m.group(2) else 1)
            wishes.append(_blank(sent, f"Сумма {int(v):,} ₽".replace(",", " "), "param", amount_rub=v)); hit = True
        if not hit:
            wishes.append(_blank(sent, sent[:28], "other", confidence=0.3))
    has_it = any(w["type"] == "theme" and "IT" in w["theme_query"] for w in wishes)
    has_div = any(w["dividends"] > 0 for w in wishes)
    if has_it and has_div:
        contr.append({"text": "IT-компании редко платят большие дивиденды. Как поступим?",
                      "option_a": "Небольшая доля IT", "option_b": "Без IT"})
    reply = "Понял: " + ", ".join(w["label"] for w in wishes if w["type"] != "other")[:200]
    return {"wishes": wishes, "contradictions": contr, "reply": reply}, _meta("interpret", t0)


def mock_theme(query: str, cards: list[str]) -> tuple[dict, dict]:
    t0 = time.time()
    q = query.lower()
    words = [w for ws in SECTOR_WORDS.values() for w in ws if w in q] or q.split()
    out = []
    for c in cards:
        cl = c.lower()
        if any(w in cl for w in words) or any(w.lower() in cl for w in query.split() if len(w) > 2):
            out.append({"secid": c.split(" | ")[0], "relevance": 0.8, "why": "подходит по отрасли и описанию"})
    return {"matches": out[:8]}, _meta("theme", t0)


def mock_mandate(f: dict) -> tuple[dict, dict]:
    t0 = time.time()
    style = "Спокойный" if f["target"].get("stability", 5) >= 6.5 else ("Ростовой" if f["target"].get("growth", 5) >= 6.5 else "Сбалансированный")
    focus = " и ".join(x["name"].lower() for x in f.get("top_sectors", [])[:2]) or "разные отрасли"
    parts = [f"{style} портфель на {f['horizon_years']} лет с упором на {focus}."]
    if f.get("drawdown_limit_rub"):
        parts.append(f"Временная просадка не глубже −{int(f['drawdown_limit_rub'] / 1000)} тыс. ₽.")
    bans = [r for r in f.get("red_lines", []) if r.startswith("Без")]
    if bans:
        parts.append("; ".join(bans[:2]) + ".")
    return {"mandate": " ".join(parts)}, _meta("mandate", t0)


def mock_explain(f: dict) -> tuple[dict, dict]:
    t0 = time.time()
    g = f.get("biggest_gap", {})
    return {"text": f"Совпадение с вашим профилем {f.get('fit', 0)}%. Сильнее всего расходится ось «{g.get('axis', '')}»: "
                    f"у бумаги {g.get('security', 0)}, вам нужно {g.get('target', 0)}."}, _meta("explain", t0)


def mock_redline(text: str) -> tuple[dict, dict]:
    t0 = time.time()
    s = text.lower()
    m = re.search(r"(\d+[.,]?\d*)\s*%", s)
    for sec, words in SECTOR_WORDS.items():
        if any(w in s for w in words):
            if m:
                return {"rl_kind": "max_sector_share", "rl_sector": sec, "rl_secid": "", "rl_value": float(m.group(1).replace(",", ".")) / 100,
                        "label": f"{SECTORS[sec]}: не больше {m.group(1)}%"}, _meta("rl", t0)
            return {"rl_kind": "exclude_sector", "rl_sector": sec, "rl_secid": "", "rl_value": 0, "label": f"Без: {SECTORS[sec].lower()}"}, _meta("rl", t0)
    if m:
        return {"rl_kind": "max_position", "rl_sector": "none", "rl_secid": "", "rl_value": float(m.group(1).replace(",", ".")) / 100,
                "label": f"Не больше {m.group(1)}% в одной бумаге"}, _meta("rl", t0)
    m = re.search(r"(\d[\d\s]*)\s*(тыс)", s)
    if "просад" in s and m:
        v = float(m.group(1).replace(" ", "")) * 1000
        return {"rl_kind": "max_drawdown_rub", "rl_sector": "none", "rl_secid": "", "rl_value": v,
                "label": f"Просадка не глубже −{int(v / 1000)} тыс. ₽"}, _meta("rl", t0)
    return {"rl_kind": "none", "rl_sector": "none", "rl_secid": "", "rl_value": 0, "label": text[:35]}, _meta("rl", t0)


def mock_rationale(f: dict) -> tuple[dict, dict]:
    t0 = time.time()
    if f.get("fit_before") is None:
        return {"text": f"Агент покупает {len(f.get('сделки', []))} бумаг, чтобы форма портфеля совпала с мандатом "
                        f"на {f.get('fit_after')}% без нарушения красных линий."}, _meta("rationale", t0)
    return {"text": f"Портфель отошёл от мандата: совпадение {f.get('fit_before')}%. "
                    f"Сделки вернут его к {f.get('fit_after')}% и не нарушат красные линии."}, _meta("rationale", t0)
