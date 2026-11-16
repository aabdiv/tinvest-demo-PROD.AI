"""Сравнение моделей на разборе пожеланий: время ответа и что модель поняла.
Нужен OPENROUTER_API_KEY в .env.  Пример:
    python tests/compare_models.py qwen/qwen3.8-27b openai/gpt-oss-120b google/gemini-3.6-flash
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import ai, config
from backend.llm import LLMError

PHRASES = [
    "Хочу стабильные дивиденды, чтобы через 5 лет был дополнительный доход. Нефть не хочу. Боюсь повторения 2022 года. Верю в российский IT.",
    "Готов рисковать ради роста на 10 лет, но без банков и не больше 10% в одной бумаге.",
    "Коплю на первый взнос через 2 года, главное — не потерять больше 30 тысяч из 600.",
]
PROFILE = {"target": {}, "red_lines": [], "themes": [], "amount_rub": 500000, "horizon_years": 5, "earlier_wishes": []}

if config.MOCK:
    sys.exit("Нужен OPENROUTER_API_KEY в .env")
models = sys.argv[1:] or [config.FAST_MODEL]
for model in models:
    config.FAST_MODEL = model
    print(f"\n=== {model}")
    total = 0
    for text in PHRASES:
        t = time.time()
        try:
            data, meta = ai.interpret(text, PROFILE)
        except LLMError as e:
            print("  ОШИБКА:", e); continue
        dt = time.time() - t; total += dt
        chips = [w["label"] for w in data.get("wishes", [])]
        print(f"  {dt:4.1f} с [{meta['mode']}, {meta.get('provider')}] {chips}")
        for c in data.get("contradictions", []):
            print(f"        противоречие: {c['text']} → {c['option_a']} / {c['option_b']}")
    print(f"  среднее время: {total / len(PHRASES):.1f} с")
