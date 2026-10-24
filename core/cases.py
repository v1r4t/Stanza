"""SQLite case store — survives agent restarts (unlike ctx.storage).

case_id = "<utr-or-noid>-<yyyymmdd>" so confirm works across restarts and
judges can be shown "Case ab12-20261024 — Day N".
"""
from __future__ import annotations
import os
import sqlite3
from datetime import datetime, timezone

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("CASES_DB") or os.path.join(_REPO_ROOT, "payresolve_cases.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  case_id TEXT PRIMARY KEY,
  sender TEXT,
  track TEXT,
  utr TEXT,
  amount REAL,
  draft TEXT,
  report TEXT,
  status TEXT DEFAULT 'open',
  created_at TEXT,
  updated_at TEXT
);
"""


def _conn() -> sqlite3.Connection:
    cx = sqlite3.connect(DB_PATH, timeout=10)
    cx.execute(_SCHEMA)
    return cx


def case_id_for(utr: str | None, occurred_on: str | None, report: str = "") -> str:
    day = (occurred_on or "")[:10] or datetime.now(timezone.utc).date().isoformat()
    day = day.replace("-", "")
    if utr:
        return f"{utr}-{day}"
    # No UTR: derive a stable suffix from the report so two distinct
    # same-day cases don't collide, while the same case stays stable.
    import hashlib
    digest = hashlib.sha256((report or "").strip().lower().encode()).hexdigest()[:8]
    return f"noid-{digest}-{day}"


def short_ref(utr: str | None, occurred_on: str | None) -> str:
    day = (occurred_on or "")[:10] or datetime.now(timezone.utc).date().isoformat()
    day = day.replace("-", "")
    return f"{utr[-4:] if utr else 'OPEN'}-{day}"


def save_case(case_id: str, sender: str, track: str, utr: str | None,
              amount: float | None, draft: str, report: str,
              status: str = "open") -> None:
    now = datetime.now(timezone.utc).isoformat()
    cx = _conn()
    try:
        cx.execute(
            """INSERT INTO cases (case_id, sender, track, utr, amount, draft, report, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(case_id) DO UPDATE SET
                 sender=excluded.sender, track=excluded.track, utr=excluded.utr,
                 amount=excluded.amount, draft=excluded.draft, report=excluded.report,
                 status=excluded.status, updated_at=excluded.updated_at""",
            (case_id, sender, track, utr, amount, draft, report, status, now, now),
        )
        cx.commit()
    finally:
        cx.close()


def get_case(case_id: str) -> dict | None:
    cx = _conn()
    try:
        cx.row_factory = sqlite3.Row
        row = cx.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        return dict(row) if row else None
    finally:
        cx.close()
