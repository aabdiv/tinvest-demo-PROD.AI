import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Быстрая ступень: разбор речи, мандат, объяснения. Умная: ночная подготовка карточек бумаг.
FAST_MODEL = os.getenv("FAST_MODEL", "qwen/qwen3.8-27b")
SMART_MODEL = os.getenv("SMART_MODEL", "moonshotai/kimi-k2.6")

# Как OpenRouter выбирает провайдера для быстрой ступени: throughput | latency | price | пусто
FAST_PROVIDER_SORT = os.getenv("FAST_PROVIDER_SORT", "throughput").strip()

# Просить модель не рассуждать перед ответом (быстрее). Если провайдер не умеет, запрос повторится без этого.
DISABLE_REASONING = os.getenv("DISABLE_REASONING", "1") == "1"

# Тестовый режим: без ключа или с MOCK_LLM=1 вместо LLM работают простые правила
MOCK = os.getenv("MOCK_LLM", "") == "1" or not OPENROUTER_API_KEY

UNIVERSE_PATH = Path(os.getenv("UNIVERSE_PATH", str(ROOT / "data" / "universe.json")))
ACCOUNT_DB_PATH = Path(os.getenv("ACCOUNT_DB_PATH", str(ROOT / "data" / "account.sqlite3")))
