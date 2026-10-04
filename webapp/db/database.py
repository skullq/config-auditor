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
    """테이블 생성 및 누락된 컬럼 마이그레이션."""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS templates (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            hostname_regex TEXT DEFAULT '',
            description TEXT DEFAULT '',
            os          TEXT DEFAULT 'iosxe',
            golden_items TEXT NOT NULL,
            conditional_rules TEXT DEFAULT '[]',
            golden_parsed TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS compare_results (
            id          TEXT PRIMARY KEY,
            hostname    TEXT,
            template_id TEXT,
            template_name TEXT,
            overall     TEXT,
            score       REAL,
            detail      TEXT,
            created_at  TEXT NOT NULL,
            bulk_job_id TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS settings (
            key         TEXT PRIMARY KEY,
            value       TEXT
        );
        """)
        
        # 마이그레이션: 기존 테이블에 컬럼이 없는 경우 추가
        # 1. templates 테이블 컬럼 확인
        cursor = conn.execute("PRAGMA table_info(templates)")
        columns = [row['name'] for row in cursor.fetchall()]
        
        needed_columns = {
            'os': "TEXT DEFAULT 'iosxe'",
            'conditional_rules': "TEXT DEFAULT '[]'",
            'interface_profiles': "TEXT DEFAULT '[]'",
            'description': "TEXT DEFAULT ''",
            'hostname_regex': "TEXT DEFAULT ''",
            'previous_snapshot': "TEXT DEFAULT ''",
            'has_pending_change': "INTEGER DEFAULT 0",
            'change_summary': "TEXT DEFAULT ''"
        }
        for col, definition in needed_columns.items():
            if col not in columns:
                conn.execute(f"ALTER TABLE templates ADD COLUMN {col} {definition}")
        
        # 2. compare_results 테이블 컬럼 확인
        cursor = conn.execute("PRAGMA table_info(compare_results)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'bulk_job_id' not in columns:
            conn.execute("ALTER TABLE compare_results ADD COLUMN bulk_job_id TEXT DEFAULT ''")


# ── Templates ──────────────────────────────────────────────────────────

def compute_template_diff(old_tpl: dict, new_items: list, new_os: str, new_name: str) -> dict:
    """기존 템플릿과 수정된 템플릿의 룰 및 속성 차이점을 계산합니다."""
    old_items = old_tpl.get("golden_items", [])
    
    def item_key(it):
        # 고유 식별자 키: block_id + command_line
        bid = it.get("block_id") or it.get("section") or ""
        cmd = it.get("command_line") or it.get("label") or ""
        return f"{bid}::{cmd.strip()}"
        
    old_map = {item_key(it): it for it in old_items if it.get("selected", True)}
    new_map = {item_key(it): it for it in new_items if it.get("selected", True)}
    
    added = []
    for k, item in new_map.items():
        if k not in old_map:
            added.append({
                "id": item.get("id"),
                "command_line": item.get("command_line", item.get("label", "")),
                "expected_value": item.get("expected_value", item.get("value", "")),
                "match_type": item.get("match_type", "exact"),
                "section": item.get("section", ""),
                "full_line_mode": bool(item.get("full_line_mode"))
            })
            
    removed = []
    for k, item in old_map.items():
        if k not in new_map:
            removed.append({
                "id": item.get("id"),
                "command_line": item.get("command_line", item.get("label", "")),
                "expected_value": item.get("expected_value", item.get("value", "")),
                "match_type": item.get("match_type", "exact"),
                "section": item.get("section", ""),
                "full_line_mode": bool(item.get("full_line_mode"))
            })
            
    modified = []
    for k, new_it in new_map.items():
        if k in old_map:
            old_it = old_map[k]
            diff_fields = {}
            new_val = str(new_it.get("expected_value", new_it.get("value", ""))).strip()
            old_val = str(old_it.get("expected_value", old_it.get("value", ""))).strip()
            if new_val != old_val:
                diff_fields["expected_value"] = {
                    "old": old_val,
                    "new": new_val
                }
            if new_it.get("match_type", "exact") != old_it.get("match_type", "exact"):
                diff_fields["match_type"] = {
                    "old": old_it.get("match_type", "exact"),
                    "new": new_it.get("match_type", "exact")
                }
            if bool(new_it.get("full_line_mode")) != bool(old_it.get("full_line_mode")):
                diff_fields["full_line_mode"] = {
                    "old": bool(old_it.get("full_line_mode")),
                    "new": bool(new_it.get("full_line_mode"))
                }
            if diff_fields:
                modified.append({
                    "id": new_it.get("id"),
                    "command_line": new_it.get("command_line", new_it.get("label", "")),
                    "section": new_it.get("section", ""),
                    "changes": diff_fields
                })
                
    has_changes = bool(added or removed or modified or (old_tpl.get("os") != new_os) or (old_tpl.get("name") != new_name))
    return {
        "has_changes": has_changes,
        "added": added,
        "removed": removed,
        "modified": modified,
        "os_changed": old_tpl.get("os") != new_os,
        "old_os": old_tpl.get("os"),
        "new_os": new_os
    }


def save_template(name: str, hostname_regex: str, description: str,
                  golden_items: list, golden_parsed: dict, os_type: str = 'iosxe', 
                  conditional_rules: list = None, interface_profiles: list = None, template_id: str = None) -> str:
    tid = template_id if template_id else str(uuid.uuid4())
    if conditional_rules is None:
        conditional_rules = []
    if interface_profiles is None:
        interface_profiles = []
        
    with get_conn() as conn:
        if template_id:
            # 기존 템플릿 및 연동된 compare_results 확인
            old_row = conn.execute("SELECT * FROM templates WHERE id=?", (tid,)).fetchone()
            has_pending = 0
            prev_snapshot = ""
            summary_json = ""
            
            if old_row:
                old_tpl = dict(old_row)
                old_tpl["golden_items"] = json.loads(old_tpl["golden_items"])
                old_tpl["conditional_rules"] = json.loads(old_tpl.get("conditional_rules", "[]"))
                old_tpl["interface_profiles"] = json.loads(old_tpl.get("interface_profiles", "[]"))
                old_tpl["golden_parsed"] = json.loads(old_tpl["golden_parsed"])
                
                # 연동된 Compare 감사 결과 확인
                cursor = conn.execute(
                    "SELECT id, hostname, overall, score, json_extract(detail, '$.filename') AS filename "
                    "FROM compare_results WHERE template_id=?", (tid,)
                )
                affected_devices = [dict(r) for r in cursor.fetchall()]
                diff = compute_template_diff(old_tpl, golden_items, os_type, name)
                
                if affected_devices and diff["has_changes"]:
                    # 연동된 감사 장비가 있고 룰 변경이 발생한 경우 -> 스냅샷 보존 및 변경 감지 활성화
                    # 기존에 이미 보존된 스냅샷이 있다면 최초 변경 전 버전을 유지
                    if old_row["previous_snapshot"]:
                        prev_snapshot = old_row["previous_snapshot"]
                    else:
                        prev_snapshot = json.dumps(old_tpl, ensure_ascii=False)
                        
                    has_pending = 1
                    summary_json = json.dumps({
                        "template_id": tid,
                        "template_name": name,
                        "diff": diff,
                        "affected_count": len(affected_devices),
                        "affected_devices": affected_devices,
                        "updated_at": datetime.utcnow().isoformat()
                    }, ensure_ascii=False)
                else:
                    # 연동된 장비가 없거나 룰 변경이 없는 경우
                    prev_snapshot = ""
                    has_pending = 0
                    summary_json = ""

            conn.execute(
                "UPDATE templates SET name=?, hostname_regex=?, description=?, os=?, "
                "golden_items=?, conditional_rules=?, interface_profiles=?, golden_parsed=?, "
                "previous_snapshot=?, has_pending_change=?, change_summary=? "
                "WHERE id=?",
                (name, hostname_regex, description, os_type,
                 json.dumps(golden_items, ensure_ascii=False),
                 json.dumps(conditional_rules, ensure_ascii=False),
                 json.dumps(interface_profiles, ensure_ascii=False),
                 json.dumps(golden_parsed, ensure_ascii=False),
                 prev_snapshot, has_pending, summary_json,
                 tid)
            )
        else:
            conn.execute(
                "INSERT INTO templates (id, name, hostname_regex, description, os, "
                "golden_items, conditional_rules, interface_profiles, golden_parsed, created_at, previous_snapshot, has_pending_change, change_summary) "
                "VALUES (?,?,?,?,?,?,?,?,?,?, '', 0, '')",
                (tid, name, hostname_regex, description, os_type,
                 json.dumps(golden_items, ensure_ascii=False),
                 json.dumps(conditional_rules, ensure_ascii=False),
                 json.dumps(interface_profiles, ensure_ascii=False),
                 json.dumps(golden_parsed, ensure_ascii=False),
                 datetime.utcnow().isoformat())
            )
    return tid


def list_templates() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, hostname_regex, description, os, created_at, "
            "has_pending_change, change_summary "
            "FROM templates ORDER BY created_at DESC"
        ).fetchall()
    res = []
    for r in rows:
        d = dict(r)
        if d.get("change_summary"):
            try:
                d["change_summary"] = json.loads(d["change_summary"])
            except Exception:
                pass
        res.append(d)
    return res


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
    d["interface_profiles"] = json.loads(d.get("interface_profiles", "[]"))
    d["golden_parsed"] = json.loads(d["golden_parsed"])
    if d.get("change_summary"):
        try:
            d["change_summary"] = json.loads(d["change_summary"])
        except Exception:
            pass
    return d


def get_pending_template_changes() -> list[dict]:
    """Compare 탭에 영향을 주며 승인/롤백 결정이 보류된 모든 템플릿 변경 목록을 조회합니다."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, os, has_pending_change, change_summary "
            "FROM templates WHERE has_pending_change=1"
        ).fetchall()
    res = []
    for r in rows:
        d = dict(r)
        if d.get("change_summary"):
            try:
                d["change_summary"] = json.loads(d["change_summary"])
            except Exception:
                pass
        res.append(d)
    return res


def rollback_template(tid: str) -> dict:
    """템플릿을 변경 전 스냅샷으로 롤백합니다."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM templates WHERE id=?", (tid,)).fetchone()
        if not row:
            raise ValueError("템플릿을 찾을 수 없습니다.")
        if not row["previous_snapshot"]:
            raise ValueError("복원할 이전 스냅샷이 존재하지 않습니다.")
            
        old_data = json.loads(row["previous_snapshot"])
        conn.execute(
            "UPDATE templates SET name=?, hostname_regex=?, description=?, os=?, "
            "golden_items=?, conditional_rules=?, golden_parsed=?, "
            "previous_snapshot='', has_pending_change=0, change_summary='' "
            "WHERE id=?",
            (old_data["name"], old_data.get("hostname_regex", ""), old_data.get("description", ""),
             old_data.get("os", "iosxe"),
             json.dumps(old_data["golden_items"], ensure_ascii=False),
             json.dumps(old_data.get("conditional_rules", []), ensure_ascii=False),
             json.dumps(old_data.get("golden_parsed", {}), ensure_ascii=False),
             tid)
        )
        return {
            "status": "rolled_back",
            "message": f"'{old_data['name']}' 템플릿이 변경 전 버전으로 성공적으로 롤백되었습니다.",
            "template_name": old_data["name"]
        }


def accept_template_change(tid: str) -> dict:
    """템플릿 변경사항을 최종 승인 상태로 확정합니다."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE templates SET previous_snapshot='', has_pending_change=0, change_summary='' WHERE id=?",
            (tid,)
        )
    return {"status": "accepted"}


def delete_template(tid: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM compare_results WHERE template_id=?", (tid,))
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
                "SELECT id, hostname, template_id, template_name, overall, score, created_at, "
                "json_extract(detail, '$.filename') AS filename "
                "FROM compare_results WHERE bulk_job_id=? ORDER BY created_at DESC",
                (bulk_job_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, hostname, template_id, template_name, overall, score, created_at, "
                "json_extract(detail, '$.filename') AS filename "
                "FROM compare_results ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
    res = []
    for r in rows:
        item = dict(r)
        if not item.get("filename"):
            item["filename"] = item.get("hostname", "")
        res.append(item)
    return res


def get_existing_filenames_for_template(template_id: str) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT json_extract(detail, '$.filename') AS filename, hostname "
            "FROM compare_results WHERE template_id=?",
            (template_id,)
        ).fetchall()
    filenames = []
    for r in rows:
        fn = r["filename"] or r["hostname"]
        if fn:
            filenames.append(fn)
    return filenames


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


def update_compare_result(rid: str, template_id: str, template_name: str,
                          overall: str, score: float, detail: dict):
    with get_conn() as conn:
        conn.execute(
            "UPDATE compare_results SET template_id=?, template_name=?, overall=?, score=?, "
            "detail=?, created_at=? WHERE id=?",
            (template_id, template_name, overall, score,
             json.dumps(detail, ensure_ascii=False),
             datetime.utcnow().isoformat(), rid)
        )


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

