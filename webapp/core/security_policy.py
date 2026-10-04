# security_policy.py — CIS Benchmark 및 DISA STIG 기반 선언적 보안 정책 관리 엔진

import os
import re
import json
import logging

logger = logging.getLogger("config-auditor.security_policy")

RULES_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "rules", "security_rules.json")
SEEDS_DIR_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "seeds", "templates")

# 메모리 내 캐시된 보안 룰셋
_CACHED_SECURITY_RULES = []


def load_security_rules(force_reload: bool = False) -> list[dict]:
    """
    rules/security_rules.json 파일로부터 글로벌 보안 기준 룰셋을 로드합니다.
    파일이 변경되었거나 최초 로드 시 캐시를 갱신합니다.
    """
    global _CACHED_SECURITY_RULES
    if _CACHED_SECURITY_RULES and not force_reload:
        return _CACHED_SECURITY_RULES

    if os.path.exists(RULES_FILE_PATH):
        try:
            with open(RULES_FILE_PATH, "r", encoding="utf-8") as f:
                rules = json.load(f)
                if isinstance(rules, list):
                    _CACHED_SECURITY_RULES = rules
                    logger.info(f"Loaded {len(rules)} security rules from {RULES_FILE_PATH}")
                    return _CACHED_SECURITY_RULES
        except Exception as e:
            logger.error(f"Failed to load security rules from {RULES_FILE_PATH}: {e}")

    # 파일이 없거나 오류 시 기본 빌트인 룰셋 반환
    _CACHED_SECURITY_RULES = get_builtin_fallback_rules()
    return _CACHED_SECURITY_RULES


def save_security_rules(rules: list[dict]) -> bool:
    """
    수정된 보안 룰셋을 rules/security_rules.json 파일에 저장(Git 형상 관리 연동)합니다.
    """
    global _CACHED_SECURITY_RULES
    try:
        os.makedirs(os.path.dirname(RULES_FILE_PATH), exist_ok=True)
        with open(RULES_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        _CACHED_SECURITY_RULES = rules
        return True
    except Exception as e:
        logger.error(f"Failed to save security rules to {RULES_FILE_PATH}: {e}")
        return False


def classify_line_risk(cmd_line: str, parent_node: str = "") -> dict:
    """
    동적 룰셋 기반으로 단일 명령어 라인의 보안 위험도를 판정합니다.
    반환값: { "level": "danger" | "warning" | "info", "title": str, "reason": str, "standard": str }
    """
    cmd = cmd_line.strip().lower()
    p_norm = parent_node.strip().lower()

    rules = load_security_rules()
    for rule in rules:
        pattern = rule.get("pattern", "")
        parent_pat = rule.get("parent_pattern", "")

        # 부모 노드 조건 검사 (지정된 경우)
        if parent_pat:
            if not re.search(parent_pat, p_norm, re.IGNORECASE):
                continue

        # 명령어 패턴 정규식 검사
        if pattern:
            if re.search(pattern, cmd, re.IGNORECASE):
                return {
                    "level": rule.get("level", "info"),
                    "title": rule.get("title", "보안 정책 위배"),
                    "reason": rule.get("reason", "보안 가이드라인에 위배되는 설정입니다."),
                    "standard": rule.get("standard", "CIS / DISA STIG"),
                    "rule_id": rule.get("id", "")
                }

    # 기본 INFO 처리
    return {
        "level": "info",
        "title": "미인가 추가 설정",
        "reason": "골든 템플릿에 정의되지 않은 설정 항목입니다.",
        "standard": "Configuration Drift",
        "rule_id": "DRIFT-INFO"
    }


def seed_templates_from_disk():
    """
    DB가 초기화되어 비어있거나 신규 환경일 때,
    seeds/templates/ 폴더 내에 저장된 골든 템플릿 JSON 파일들을 자동으로 DB에 시딩합니다.
    """
    from webapp.db.database import list_templates, save_template

    if not os.path.exists(SEEDS_DIR_PATH):
        return 0

    existing_tpls = list_templates()
    existing_names = {t["name"] for t in existing_tpls}
    seeded_count = 0

    for fname in os.listdir(SEEDS_DIR_PATH):
        if fname.endswith(".json"):
            fpath = os.path.join(SEEDS_DIR_PATH, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    name = data.get("name")
                    if name and name not in existing_names:
                        save_template(
                            name=name,
                            hostname_regex=data.get("hostname_regex", ".*"),
                            description=data.get("description", "Git Seed에서 자동 등록된 표준 템플릿"),
                            os_type=data.get("os", "iosxe"),
                            selected_items=data.get("golden_items", []),
                            conditional_rules=data.get("conditional_rules", []),
                            interface_profiles=data.get("interface_profiles", []),
                            golden_parsed=data.get("golden_parsed", {})
                        )
                        existing_names.add(name)
                        seeded_count += 1
                        logger.info(f"Seeded template '{name}' from {fname}")
            except Exception as e:
                logger.error(f"Error seeding template from {fpath}: {e}")

    return seeded_count


def export_template_to_seed(template_id: str, custom_filename: str = None) -> str:
    """
    DB에 저장된 골든 템플릿을 seeds/templates/<filename>.json 파일로 내보내어
    Git으로 버전 관리할 수 있도록 합니다.
    """
    from webapp.db.database import get_template

    tpl = get_template(template_id)
    if not tpl:
        raise ValueError(f"Template ID '{template_id}' not found.")

    os.makedirs(SEEDS_DIR_PATH, exist_ok=True)
    fname = custom_filename or f"{re.sub(r'[^a-zA-Z0-9_-]', '_', tpl['name']).lower()}.json"
    if not fname.endswith(".json"):
        fname += ".json"

    fpath = os.path.join(SEEDS_DIR_PATH, fname)
    seed_data = {
        "name": tpl["name"],
        "description": tpl.get("description", ""),
        "os": tpl.get("os", "iosxe"),
        "hostname_regex": tpl.get("hostname_regex", ".*"),
        "golden_items": tpl.get("golden_items", []),
        "interface_profiles": tpl.get("interface_profiles", []),
        "golden_parsed": tpl.get("golden_parsed", {}),
        "conditional_rules": tpl.get("conditional_rules", [])
    }

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(seed_data, f, ensure_ascii=False, indent=2)

    return fpath


def get_builtin_fallback_rules() -> list[dict]:
    """기본 빌트인 하드코딩 폴백 룰셋"""
    return [
        {
            "id": "FALLBACK-PRIV15",
            "level": "danger",
            "standard": "CIS 1.1",
            "title": "비인가 최고 관리자(Priv 15) 계정",
            "pattern": r"\busername\s+\S+.*\b(privilege|priv)\s+15\b",
            "reason": "Privilege 15 최고 권한 로컬 계정이 추가되어 백도어 위험이 있습니다."
        },
        {
            "id": "FALLBACK-SNMP-RW",
            "level": "danger",
            "standard": "CIS 1.3",
            "title": "SNMP 쓰기(RW) 권한 노출",
            "pattern": r"\bsnmp-server\s+community\s+\S+.*\b(rw|write)\b",
            "reason": "SNMP 쓰기 권한이 부여되어 비인가자에 의한 원격 장비 설정 변경이 가능합니다."
        },
        {
            "id": "FALLBACK-TELNET",
            "level": "danger",
            "standard": "CIS 1.2",
            "title": "Telnet 원격 접속 허용",
            "pattern": r"transport\s+input\s+.*(telnet|all)",
            "reason": "평문 전송 프로토콜인 Telnet 접속이 허용되어 계정 탈취 위험이 있습니다."
        }
    ]
