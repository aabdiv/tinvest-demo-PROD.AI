"""Local readiness check; makes no paid LLM calls and changes no portfolios."""
import json
from urllib.request import urlopen


def main():
    with urlopen("http://127.0.0.1:8000/api/meta", timeout=3) as response:
        meta = json.load(response)
    if not meta.get("universe", {}).get("ok") or not meta["universe"].get("count"):
        raise SystemExit("Securities universe is not ready.")


if __name__ == "__main__":
    main()
