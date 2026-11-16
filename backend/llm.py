"""Структурированные вызовы LLM через OpenRouter (OpenAI-совместимый API).

Порядок попыток:
1) json_schema (strict) + require_parameters + без рассуждений;
2) json_schema (strict) + require_parameters;
3) json_object со схемой в промпте (если провайдеры модели не умеют json_schema).
"""
import json
import logging
import re
import time

from openai import OpenAI

from . import config

log = logging.getLogger("llm")
_client = None


class LLMError(RuntimeError):
    pass


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=config.OPENROUTER_BASE_URL,
            api_key=config.OPENROUTER_API_KEY,
            timeout=60,
            default_headers={"HTTP-Referer": "http://localhost:8000", "X-Title": "T-Invest Premarket MVP"},
        )
    return _client


def parse_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


_MANDATORY_REASONING: set[str] = set()  # модели, у которых нельзя выключить рассуждения


class _Truncated(Exception):
    pass


def structured(tier: str, system: str, user: str, schema_name: str, schema: dict,
               max_tokens: int = 1500, temperature: float = 0.2) -> tuple[dict, dict]:
    """Возвращает (данные, мета). Мета: модель, время в мс, режим, провайдер.

    Если модель не даёт выключить рассуждения, она запоминается: дальше рассуждения идут на минимуме,
    а лимит токенов увеличивается, чтобы рассуждения не съели место под JSON.
    Если ответ оборвался или JSON битый — тот же режим повторяется один раз с удвоенным лимитом.
    """
    model = config.FAST_MODEL if tier == "fast" else config.SMART_MODEL
    provider = {"require_parameters": True}
    if tier == "fast" and config.FAST_PROVIDER_SORT:
        provider["sort"] = config.FAST_PROVIDER_SORT
    rf_schema = {"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": schema}}

    plan = (["noreason"] if config.DISABLE_REASONING and model not in _MANDATORY_REASONING else []) + ["schema", "object"]
    t0 = time.time()
    last_err = None
    tokens = max_tokens
    i = 0
    while i < len(plan):
        mode = plan[i]
        mandatory = model in _MANDATORY_REASONING
        extra = {"provider": dict(provider)}
        rf, sys_msg = rf_schema, system
        if mode == "noreason":
            extra["reasoning"] = {"enabled": False}
        elif mandatory:
            extra["reasoning"] = {"effort": "low"}
        if mode == "object":
            rf = {"type": "json_object"}
            extra["provider"].pop("require_parameters", None)
            sys_msg = system + "\n\nОтвечай ТОЛЬКО одним JSON-объектом строго по этой JSON-схеме:\n" + json.dumps(schema, ensure_ascii=False)
        budget = tokens * (4 if mandatory else 1)
        try:
            resp = _get_client().chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": user}],
                max_tokens=budget,
                temperature=temperature,
                response_format=rf,
                extra_body=extra,
            )
            choice = resp.choices[0]
            content = choice.message.content or ""
            if getattr(choice, "finish_reason", None) == "length":
                raise _Truncated(f"ответ оборван на лимите {budget} токенов")
            data = parse_json(content)
            meta = {
                "model": getattr(resp, "model", model),
                "ms": int((time.time() - t0) * 1000),
                "mode": "json_schema" if mode != "object" else "json_object",
                "provider": getattr(resp, "provider", None),
                "tier": tier,
            }
            log.info("LLM %s %s %sms via %s", schema_name, meta["model"], meta["ms"], meta["provider"])
            return data, meta
        except Exception as e:
            last_err = e
            msg = str(e)
            if "Reasoning is mandatory" in msg or "cannot be disabled" in msg:
                _MANDATORY_REASONING.add(model)
                log.info("LLM %s: у модели нельзя выключить рассуждения, дальше — на минимуме", model)
                i += 1
                continue
            if isinstance(e, (json.JSONDecodeError, _Truncated)) and tokens == max_tokens:
                log.warning("LLM %s: %s — повторяю с большим лимитом", schema_name, e)
                tokens *= 2
                continue
            log.warning("LLM %s попытка %s не удалась: %s", schema_name, mode, e)
            i += 1
    raise LLMError(f"Не удалось получить ответ модели {model}: {last_err}")
