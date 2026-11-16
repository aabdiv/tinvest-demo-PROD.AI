"""Persistent, local single-user portfolio cabinet (no brokerage connection)."""
import datetime as dt
import json
import sqlite3
from contextlib import contextmanager
from uuid import uuid4

from . import config


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connection():
    config.ACCOUNT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(config.ACCOUNT_DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS portfolios (id TEXT PRIMARY KEY, data TEXT NOT NULL, revision INTEGER NOT NULL)")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def unpack(row):
    return {**json.loads(row["data"]), "id": row["id"], "revision": row["revision"]}


def list_all():
    with connection() as db:
        return [unpack(r) for r in db.execute("SELECT * FROM portfolios ORDER BY rowid")]


def get(portfolio_id):
    with connection() as db:
        row = db.execute("SELECT * FROM portfolios WHERE id = ?", (portfolio_id,)).fetchone()
        return unpack(row) if row else None


def create(data, portfolio_id=None):
    portfolio_id = portfolio_id or uuid4().hex
    data = {**data, "created_at": now(), "updated_at": now()}
    with connection() as db:
        db.execute("INSERT INTO portfolios VALUES (?, ?, 1)", (portfolio_id, json.dumps(data, ensure_ascii=False)))
    return {**data, "id": portfolio_id, "revision": 1}


def update(record, expected_revision):
    data = {k: v for k, v in record.items() if k not in ("id", "revision")}
    data["updated_at"] = now()
    with connection() as db:
        cursor = db.execute(
            "UPDATE portfolios SET data = ?, revision = revision + 1 WHERE id = ? AND revision = ?",
            (json.dumps(data, ensure_ascii=False), record["id"], expected_revision),
        )
        if cursor.rowcount != 1:
            return None
    return {**data, "id": record["id"], "revision": expected_revision + 1}
