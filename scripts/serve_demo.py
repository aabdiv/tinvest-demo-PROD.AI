"""Container startup: reject accidental mock mode and verify persistent storage."""
import os
import sqlite3

from backend import config
from backend.universe import get_universe


def preflight():
    if not config.OPENROUTER_API_KEY and os.getenv("MOCK_LLM") != "1":
        raise SystemExit("Set OPENROUTER_API_KEY, or explicitly set MOCK_LLM=1 for an offline demo.")
    if not get_universe().N:
        raise SystemExit("The securities universe is empty.")
    config.ACCOUNT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Check write permissions even when a database was imported into the volume.
    with sqlite3.connect(config.ACCOUNT_DB_PATH) as db:
        db.execute("CREATE TABLE IF NOT EXISTS _demo_storage_check (id INTEGER)")
        db.execute("DROP TABLE _demo_storage_check")


def main():
    preflight()
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, workers=1, proxy_headers=False)


if __name__ == "__main__":
    main()
