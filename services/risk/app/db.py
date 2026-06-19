"""SQLite persistence for the web app (plan §A): users + cases + case documents.

Stdlib sqlite3 only (no ORM dep). The DB file lives under a gitignored dir and is created
on first use. All local — no network. Stores the audit trail of every submission (roadmap F1).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "app_data" / "trustshield.db"


def _db_path() -> Path:
    """Resolved DB path — read from env at call time so tests can redirect it."""
    return Path(os.environ.get("TRUSTSHIELD_DB", str(_DEFAULT_DB)))


def _conn() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id         TEXT PRIMARY KEY,
                email      TEXT UNIQUE NOT NULL,
                pw_hash    TEXT NOT NULL,
                pw_salt    TEXT NOT NULL,
                role       TEXT NOT NULL DEFAULT 'user',
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cases (
                id            TEXT PRIMARY KEY,
                user_id       TEXT NOT NULL,
                user_email    TEXT NOT NULL,
                purpose       TEXT NOT NULL,
                status        TEXT NOT NULL,
                trust_score   REAL,
                action        TEXT,
                decision_json TEXT,
                overlays_json TEXT,
                verification_json TEXT,
                loan_amount   REAL,
                tenure_months INTEGER,
                created_at    REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS case_docs (
                id          TEXT PRIMARY KEY,
                case_id     TEXT NOT NULL,
                filename    TEXT NOT NULL,
                doc_type    TEXT,
                fields_json TEXT,
                kyc_json    TEXT,
                FOREIGN KEY (case_id) REFERENCES cases(id)
            );
            """
        )
        _migrate(c)


def _migrate(c: sqlite3.Connection) -> None:
    """Additively add columns introduced after the first release (plan §9). Idempotent."""
    have = {r["name"] for r in c.execute("PRAGMA table_info(cases)").fetchall()}
    for col, decl in (("verification_json", "TEXT"),
                      ("loan_amount", "REAL"),
                      ("tenure_months", "INTEGER")):
        if col not in have:
            c.execute(f"ALTER TABLE cases ADD COLUMN {col} {decl}")


# ----------------------------------------------------------------- users
def create_user(email: str, pw_hash: str, pw_salt: str, role: str = "user") -> dict:
    uid = f"usr_{uuid.uuid4().hex[:12]}"
    with _conn() as c:
        c.execute(
            "INSERT INTO users (id, email, pw_hash, pw_salt, role, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uid, email.lower().strip(), pw_hash, pw_salt, role, time.time()),
        )
    return {"id": uid, "email": email.lower().strip(), "role": role}


def get_user_by_email(email: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
    return dict(row) if row else None


def count_users() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]


# ----------------------------------------------------------------- cases
def create_case(
    case_id: str, user_id: str, user_email: str, purpose: str, status: str,
    trust_score: Optional[float], action: Optional[str],
    decision_json: Optional[str], overlays_json: Optional[str],
    verification_json: Optional[str] = None,
    loan_amount: Optional[float] = None,
    tenure_months: Optional[int] = None,
) -> str:
    with _conn() as c:
        c.execute(
            "INSERT INTO cases (id, user_id, user_email, purpose, status, trust_score, action, "
            "decision_json, overlays_json, verification_json, loan_amount, tenure_months, "
            "created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (case_id, user_id, user_email, purpose, status, trust_score, action,
             decision_json, overlays_json, verification_json, loan_amount, tenure_months,
             time.time()),
        )
    return case_id


def add_case_doc(case_id: str, filename: str, doc_type: Optional[str],
                 fields_json: Optional[str], kyc_json: Optional[str]) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO case_docs (id, case_id, filename, doc_type, fields_json, kyc_json) "
            "VALUES (?,?,?,?,?,?)",
            (f"cd_{uuid.uuid4().hex[:12]}", case_id, filename, doc_type, fields_json, kyc_json),
        )


def list_cases(user_id: Optional[str] = None) -> list[dict]:
    """All cases (admin) when user_id is None, else only that user's. Summary rows only."""
    q = ("SELECT id, user_email, purpose, status, trust_score, action, created_at "
         "FROM cases {} ORDER BY created_at DESC")
    with _conn() as c:
        if user_id:
            rows = c.execute(q.format("WHERE user_id = ?"), (user_id,)).fetchall()
        else:
            rows = c.execute(q.format(""), ()).fetchall()
    return [dict(r) for r in rows]


def get_case(case_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if not row:
            return None
        case = dict(row)
        docs = c.execute("SELECT filename, doc_type, fields_json, kyc_json FROM case_docs "
                         "WHERE case_id = ?", (case_id,)).fetchall()
    case["documents"] = [
        {
            "filename": d["filename"], "doc_type": d["doc_type"],
            "fields": json.loads(d["fields_json"]) if d["fields_json"] else {},
            "kyc": json.loads(d["kyc_json"]) if d["kyc_json"] else {},
        }
        for d in docs
    ]
    return case
