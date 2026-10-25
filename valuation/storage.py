"""Local-only saved analyses. No credentials or remote writes."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB = Path(os.environ.get("VALUATION_DB", Path(__file__).resolve().parents[1]/"data"/"analyses.sqlite3"))


def connection():
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS analyses (id INTEGER PRIMARY KEY, name TEXT NOT NULL, created TEXT NOT NULL, payload TEXT NOT NULL)")
    return con


def save(name, payload):
    with connection() as con:
        con.execute("INSERT INTO analyses (name,created,payload) VALUES (?,?,?)",
                    (name[:120],datetime.now(timezone.utc).isoformat(),json.dumps(payload,allow_nan=False)))


def list_saved():
    with connection() as con:
        return con.execute("SELECT id,name,created FROM analyses ORDER BY id DESC LIMIT 100").fetchall()


def load(analysis_id):
    with connection() as con:
        row = con.execute("SELECT payload FROM analyses WHERE id=?",(analysis_id,)).fetchone()
    if not row:
        raise ValueError("Saved analysis not found.")
    return json.loads(row[0])
