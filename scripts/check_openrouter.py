"""Run on the target VPS: one small structured request through the app's LLM path."""
import sys

from backend import config, llm


def main():
    if config.MOCK:
        print("Set OPENROUTER_API_KEY and MOCK_LLM=0 before checking OpenRouter.", file=sys.stderr)
        return 1
    # Disable HTTP retries and application logging for this check; never print secrets
    # or raw provider errors. structured() may still try its format fallbacks.
    import logging

    logging.disable(logging.CRITICAL)
    llm._get_client().max_retries = 0
    try:
        data, meta = llm.structured(
            "fast", "Return only JSON matching the schema.", 'Return {"ok": true}.',
            "deployment_check",
            {"type": "object", "properties": {"ok": {"type": "boolean"}},
             "required": ["ok"], "additionalProperties": False},
            max_tokens=128, temperature=0,
        )
    except llm.LLMError:
        print("OpenRouter check failed. Check network access, key, balance, model and provider availability.", file=sys.stderr)
        return 1
    if data.get("ok") is not True:
        print("OpenRouter returned an unexpected result.", file=sys.stderr)
        return 1
    print(f"OpenRouter OK: {meta['model']}, {meta['mode']}, {meta['ms']} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
