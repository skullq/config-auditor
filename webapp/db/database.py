"""
db/database.py + db/models.py 통합
SQLite DB 초기화 및 모델 정의.
"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """테이블 생성 (없으면)."""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS templates (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            hostname_regex TEXT DEFAULT '',
            description TEXT DEFAULT '',
            os          TEXT DEFAULT 'iosxe', -- iosxe, nxos, iosxr, aireos 등
            golden_items TEXT NOT NULL,       -- JSON (기본 항목)
            conditional_rules TEXT DEFAULT '[]', -- JSON (조건부 규칙: if regex then expect items)
            golden_parsed TEXT NOT NULL,      -- JSON (원본 분석)
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS compare_results (
            id          TEXT PRIMARY KEY,
            hostname    TEXT,
            template_id TEXT,
            template_name TEXT,
            overall     TEXT,
            score       REAL,
            detail      TEXT,             -- JSON
            created_at  TEXT NOT NULL,
            bulk_job_id TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS settings (
            key         TEXT PRIMARY KEY,
            value       TEXT
        );
        """)


# ── Templates ──────────────────────────────────────────────────────────

def save_template(name: str, hostname_regex: str, description: str,
                  golden_items: list, golden_parsed: dict, os_type: str = 'iosxe', 
                  conditional_rules: list = None, template_id: str = None) -> str:
    tid = template_id if template_id else str(uuid.uuid4())
    if conditional_rules is None:
        conditional_rules = []
    with get_conn() as conn:
        if template_id:
            conn.execute(
                "UPDATE templates SET name=?, hostname_regex=?, description=?, os=?, "
                "golden_items=?, conditional_rules=?, golden_parsed=? "
                "WHERE id=?",
                (name, hostname_regex, description, os_type,
                 json.dumps(golden_items, ensure_ascii=False),
                 json.dumps(conditional_rules, ensure_ascii=False),
                 json.dumps(golden_parsed, ensure_ascii=False),
                 tid)
            )
        else:
            conn.execute(
                "INSERT INTO templates (id, name, hostname_regex, description, os, "
                "golden_items, conditional_rules, golden_parsed, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (tid, name, hostname_regex, description, os_type,
                 json.dumps(golden_items, ensure_ascii=False),
                 json.dumps(conditional_rules, ensure_ascii=False),
                 json.dumps(golden_parsed, ensure_ascii=False),
                 datetime.utcnow().isoformat())
            )
    return tid


def list_templates() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, hostname_regex, description, created_at "
            "FROM templates ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_template(tid: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM templates WHERE id=?", (tid,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["golden_items"] = json.loads(d["golden_items"])
    d["conditional_rules"] = json.loads(d.get("conditional_rules", "[]"))
    d["golden_parsed"] = json.loads(d["golden_parsed"])
    return d


def delete_template(tid: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM templates WHERE id=?", (tid,))


# ── Compare Results ────────────────────────────────────────────────────

def save_compare_result(hostname: str, template_id: str, template_name: str,
                        overall: str, score: float, detail: dict,
                        bulk_job_id: str = "") -> str:
    rid = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO compare_results "
            "(id, hostname, template_id, template_name, overall, score, "
            "detail, created_at, bulk_job_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (rid, hostname, template_id, template_name, overall, score,
             json.dumps(detail, ensure_ascii=False),
             datetime.utcnow().isoformat(), bulk_job_id)
        )
    return rid


def list_compare_results(bulk_job_id: str = "") -> list[dict]:
    with get_conn() as conn:
        if bulk_job_id:
            rows = conn.execute(
                "SELECT id, hostname, template_name, overall, score, created_at "
                "FROM compare_results WHERE bulk_job_id=? ORDER BY created_at DESC",
                (bulk_job_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, hostname, template_name, overall, score, created_at "
                "FROM compare_results ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
    return [dict(r) for r in rows]


def get_compare_result(rid: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM compare_results WHERE id=?", (rid,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["detail"] = json.loads(d["detail"])
    return d

def delete_compare_result(rid: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM compare_results WHERE id=?", (rid,))


# ── Settings ───────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )

# ── Backup & Reset ─────────────────────────────────────────────────────

def reset_db_data():
    """DB 초기화: 데이터 삭제 (사용자 설정 외 모든 결과/템플릿 삭제)"""
    with get_conn() as conn:
        conn.execute("DELETE FROM compare_results")
        conn.execute("DELETE FROM templates")
        # settings는 유지 또는 초기화할 수 있지만, 기본적으로 data.db 자체를 핸들링하는 것으로 가능.

