"""SQLite store shared by the batch job and the web app: subscribers and job runs."""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager

from harness.common import DATA, iso, now_ist

DB = DATA / "app" / "app.db"
EMAIL = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")


@contextmanager
def db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT, interests TEXT,
            created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending');
        CREATE TABLE IF NOT EXISTS job_runs (
            id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, steps TEXT);
    """)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def add_subscriber(email: str, name: str = "", interests: list[str] | None = None) -> tuple[bool, str]:
    email = (email or "").strip().lower()
    if not EMAIL.match(email):
        return False, "Please enter a valid email address."
    with db() as con:
        cur = con.execute("INSERT OR IGNORE INTO subscribers(email, name, interests, created_at) VALUES (?,?,?,?)",
                          (email, (name or "").strip()[:80], json.dumps(interests or []), iso(now_ist())))
        if cur.rowcount == 0:
            return True, "You're already on the list."
    return True, "You're subscribed. New issues will be listed here for you."


def subscriber_count() -> int:
    with db() as con:
        return con.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]


def list_subscribers() -> list[dict]:
    with db() as con:
        return [dict(r) for r in con.execute("SELECT email, name, interests, created_at, status FROM subscribers ORDER BY id")]


def start_job() -> int:
    with db() as con:
        return con.execute("INSERT INTO job_runs(started_at, status, steps) VALUES (?,?,?)",
                           (iso(now_ist()), "running", "{}")).lastrowid


def finish_job(job_id: int, status: str, steps: dict) -> None:
    with db() as con:
        con.execute("UPDATE job_runs SET finished_at=?, status=?, steps=? WHERE id=?",
                    (iso(now_ist()), status, json.dumps(steps), job_id))


def last_jobs(n: int = 5) -> list[dict]:
    with db() as con:
        rows = con.execute("SELECT * FROM job_runs ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    return [{**dict(r), "steps": json.loads(r["steps"] or "{}")} for r in rows]


def unsubscribe(email: str) -> bool:
    with db() as con:
        return con.execute("UPDATE subscribers SET status='unsubscribed' WHERE email=?", (email.strip().lower(),)).rowcount > 0
