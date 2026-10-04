"""
core/comparator.py
골든 템플릿 항목과 타겟 설정을 비교하여 Pass / Review / Fail 결과 및
추가된 불필요/보안 위협 설정(Extra & Rogue Config)의 Diff 및 롤백 로직 생성.
"""

import re
from typing import Any, Dict, List, Tuple


def _normalize_banner(text: str) -> str:
    """Cisco 배너의 시작/종료 구분자 및 불필요한 공백 제거."""
    if not text:
        return ""
    lines = text.strip().splitlines()
    if not lines:
        return ""

    first_line = lines[0].strip()
    if first_line.lower().startswith('banner '):
        parts = first_line.split()
        if len(parts) >= 3:
            idx = first_line.find(parts[1]) + len(parts[1])
            content_start = first_line[idx:].lstrip()
            if content_start:
                delim = content_start[0]
                lines[0] = content_start.lstrip(delim).strip()

    if lines:
        last_line = lines[-1].strip()
        if last_line and (len(last_line) == 1 or last_line.endswith('^C')):
            lines[-1] = last_line.rstrip('^C').strip()

    return "\n".join(l.strip() for l in lines if l.strip())


def _is_same_normalized(a: str, b: str) -> bool:
    """공백 종류, 개수, 대소문자 차이를 완전히 무시하고 실질적인 의미가 동일한지 확인."""
    if not a or not b:
        return a == b
    norm_a = re.sub(r'[\s\u00A0\t\n\r]+', ' ', str(a).strip()).lower()
    norm_b = re.sub(r'[\s\u00A0\t\n\r]+', ' ', str(b).strip()).lower()
    return norm_a == norm_b


def _normalize_parent(parent_str: str) -> str:
    """부모 노드 식별자 정규화 (대소문자, 공백, 인터페이스 축약형 보정)."""
    s = re.sub(r'\s+', ' ', str(parent_str).strip().lower())
    s = re.sub(r'^interface\s+gi(?:gabitethernet)?', 'interface gigabitethernet', s)
    s = re.sub(r'^interface\s+te(?:ngigabitethernet)?', 'interface tengigabitethernet', s)
    s = re.sub(r'^interface\s+fo(?:rtengigabitethernet)?', 'interface fortygigabitethernet', s)
    s = re.sub(r'^interface\s+hu(?:ndredgige)?', 'interface hundredgige', s)
    s = re.sub(r'^interface\s+lo(?:opback)?', 'interface loopback', s)
    s = re.sub(r'^interface\s+tu(?:nnel)?', 'interface tunnel', s)
    s = re.sub(r'^interface\s+vl(?:an)?', 'interface vlan', s)
    return s


def _normalize_cmd_line(line: str) -> str:
    """명령어 라인 정규화."""
    return re.sub(r'\s+', ' ', str(line).strip().lower())


def _match_value(expected: Any, actual_value: Any, match_type: str, section: str = "") -> tuple[bool, str]:
    """
    값 비교 및 UI에 표시할 실제 값(display_actual) 반환.
    """
    exp_str = str(expected).strip()
    act_full = str(actual_value).strip() if actual_value is not None else ""

    if not act_full:
        return (False, "(없음)")

    # 배너 특수 처리
    if section == "banner":
        norm_exp = _normalize_banner(exp_str)
        norm_act = _normalize_banner(act_full)
        if norm_exp == norm_act or norm_exp in norm_act:
            return (True, "(배너 일치)" if norm_exp == norm_act else "(배너 포함)")
        return (False, act_full.splitlines()[0] + "..." if len(act_full.splitlines()) > 1 else act_full)

    lines = [l.strip() for l in act_full.splitlines() if l.strip()]

    if match_type == "exists":
        if lines:
            return (True, f"(존재함: {lines[0]})")
        elif act_full:
            return (True, f"(존재함: {act_full})")
        return (False, "(미존재)")

    if match_type == "exact":
        for line in lines:
            if _is_same_normalized(exp_str, line):
                return (True, line)
        if _is_same_normalized(exp_str, act_full):
            return (True, act_full)
        return (False, lines[0] if len(lines) > 0 else "(불일치)")

    if match_type == "regex":
        try:
            pattern = re.compile(exp_str, re.I)
            for line in lines:
                if pattern.search(line):
                    return (True, line)
            if pattern.search(act_full):
                return (True, "(정규식 일치)")
            return (False, lines[0] if len(lines) > 0 else "(미일치)")
        except re.error as e:
            return (False, f"(Regex 에러: {e})")

    if match_type == "contains":
        keyword = exp_str.strip('*').strip() if exp_str.startswith('*') or exp_str.endswith('*') else exp_str
        low_kw = keyword.lower()
        for line in lines:
            if low_kw in line.lower() or _is_same_normalized(keyword, line):
                return (True, line)
        if low_kw in act_full.lower():
            return (True, "(블록 내 포함)")
        return (False, lines[0] if len(lines) > 0 else "(불일치)")

    # 기본값 (평문 비교)
    matched = _is_same_normalized(exp_str, act_full)
    if not matched and len(lines) > 0:
        for line in lines:
            if _is_same_normalized(exp_str, line):
                return (True, line)
        if exp_str.lower() in act_full.lower():
            return (True, "(블록 내 포함-F)")

    return (matched, act_full if matched else (lines[0] + "..." if len(lines) > 0 else "(불일치)"))


def _extract_target_inventory(target_parsed: dict) -> dict:
    """타겟 설정의 구조화된 계층 인덱스 생성."""
    inventory = {
        "parents": {},        # norm_parent -> list of dict(id, line, value, raw, item)
        "globals": [],        # list of dict(id, line, value, raw, item)
        "items_by_id": {},    # id -> item
        "all_items": []       # list of item
    }

    blocks = target_parsed.get("blocks", [])
    for b in blocks:
        for it in b.get("items", []):
            inventory["items_by_id"][it["id"]] = it
            inventory["all_items"].append(it)
            p_node = (it.get("parent_node") or "").strip()
            c_line = (it.get("command_line") or it.get("label") or "").strip()
            if " > " in c_line and not it.get("command_line"):
                c_line = c_line.split(" > ")[-1].strip()
            val = it.get("value", "")

            entry = {
                "id": it["id"],
                "line": c_line,
                "value": val,
                "raw": it.get("raw_block", ""),
                "item": it
            }

            if p_node:
                norm_p = _normalize_parent(p_node)
                if norm_p not in inventory["parents"]:
                    inventory["parents"][norm_p] = []
                inventory["parents"][norm_p].append(entry)
            else:
                inventory["globals"].append(entry)

    return inventory


def _find_target_actual(item: dict, inventory: dict, target_sections: dict) -> tuple[Any, str, str]:
    """
    골든 아이템의 parent_node 및 command_line을 바탕으로 타겟 설정에서 실제 설정값을 지능적으로 검색.
    반환값: (actual_value, found_line_context, matched_target_id)
    """
    item_id = item.get("id", "")
    section = item.get("section", "")
    p_node = (item.get("parent_node") or "").strip()
    c_line = (item.get("command_line") or item.get("label") or "").strip()
    if " > " in c_line and not item.get("command_line"):
        c_line = c_line.split(" > ")[-1].strip()

    # 1. ID로 직접 일치하는 경우
    if item_id in inventory["items_by_id"]:
        it = inventory["items_by_id"][item_id]
        return it.get("value"), it.get("command_line", c_line), it.get("id", "")

    # 2. 부모 노드가 있는 경우 (Interface, BGP, OSPF, Line, VRF, ACL 등)
    if p_node:
        norm_p = _normalize_parent(p_node)
        target_children = inventory["parents"].get(norm_p, [])
        if not target_children:
            for tp_key, tp_list in inventory["parents"].items():
                if tp_key == norm_p or tp_key.endswith(" " + norm_p) or norm_p.endswith(" " + tp_key):
                    target_children = tp_list
                    break

        if target_children:
            # 2-1. 명령어 전체 일치
            for c in target_children:
                if _is_same_normalized(c["line"], c_line):
                    return c.get("value"), c["line"], c.get("id", "")

            # 2-2. 명령어 키워드 접두사 일치
            cmd_parts = c_line.split()
            if cmd_parts:
                first_word = cmd_parts[0].lower()
                prefix = f"{first_word} {cmd_parts[1].lower()}" if len(cmd_parts) >= 2 else first_word
                for c in target_children:
                    t_line = c["line"].lower()
                    if t_line.startswith(prefix + " ") or t_line == prefix:
                        return c.get("value"), c["line"], c.get("id", "")

            # 2-3. 네트워크 대역 명령어
            if c_line.lower().startswith("network "):
                for c in target_children:
                    if c["line"].lower().startswith("network ") and _is_same_normalized(c["line"], c_line):
                        return c.get("value"), c["line"], c.get("id", "")

        return None, "", ""

    # 3. 부모 노드가 없는 글로벌 명령어 (hostname, version, service, ntp 등)
    cmd_parts = c_line.split()
    if cmd_parts:
        first_word = cmd_parts[0].lower()
        prefix = f"{first_word} {cmd_parts[1].lower()}" if len(cmd_parts) >= 2 else first_word
        for g in inventory["globals"]:
            g_line = g["line"]
            if _is_same_normalized(g_line, c_line):
                return g.get("value"), g_line, g.get("id", "")
            if g_line.lower().startswith(prefix + " ") or g_line.lower() == prefix:
                return g.get("value"), g_line, g.get("id", "")
            if g_line.lower().startswith(first_word + " "):
                return g.get("value"), g_line, g.get("id", "")

    # 4. Fallback: 타겟의 raw 섹션 텍스트에서 검색
    target_entry = target_sections.get(section, {})
    if "raw" in target_entry:
        raw_list = target_entry["raw"]
        raw_full = "\n".join(raw_list) if isinstance(raw_list, list) else str(raw_list)
        for line in raw_full.splitlines():
            s_line = line.strip()
            if _is_same_normalized(s_line, c_line):
                return s_line, s_line, ""

    return None, "", ""


# ════════════════════════════════════════════════════════════════════════
# 보안 위험도 분석 및 롤백 CLI 명령어 생성 엔진 (CIS Benchmark & DISA STIG)
# ════════════════════════════════════════════════════════════════════════

def classify_risk(cmd_line: str, parent_node: str = "") -> dict:
    """
    선언적 보안 정책 엔진(rules/security_rules.json)을 통해 
    추가된 명령어 라인의 보안 위험도 및 필요성을 CIS Benchmark / DISA STIG 기준으로 분석.
    반환값: { "level": "danger" | "warning" | "info", "title": str, "reason": str, "standard": str }
    """
    try:
        from core.security_policy import classify_line_risk
        return classify_line_risk(cmd_line, parent_node)
    except Exception:
        pass

    # 로드 실패 시 빌트인 기본 패턴 매칭
    cmd = cmd_line.strip().lower()
    p_norm = parent_node.strip().lower()

    # 1. CRITICAL / DANGER (치명적 보안 위협)
    # 1-1. SNMP 커뮤니티 취약점
    if re.search(r'\bsnmp-server\s+community\b', cmd):
        if re.search(r'\b(rw|write)\b', cmd):
            return {
                "level": "danger",
                "title": "SNMP 쓰기(RW) 권한 노출",
                "reason": "SNMP 쓰기 권한이 부여되어 비인가자에 의한 원격 장비 설정 변경이 가능합니다."
            }
        if re.search(r'\b(public|private)\b', cmd):
            return {
                "level": "danger",
                "title": "기본 SNMP 커뮤니티 사용",
                "reason": "유추하기 쉬운 기본 SNMP 커뮤니티 문자열(public/private)이 활성화되어 있습니다."
            }

    # 1-2. 비인가 최고 권한 계정 (Privilege 15)
    if re.search(r'\busername\s+\S+\b', cmd) and re.search(r'\b(privilege|priv)\s+15\b', cmd):
        return {
            "level": "danger",
            "title": "비인가 최고 관리자(Priv 15) 계정",
            "reason": "골든 룰에 등록되지 않은 Privilege 15 최고 권한 로컬 계정이 추가되어 백도어 위험이 있습니다."
        }

    # 1-3. 비암호화 원격 접속 (Telnet / HTTP)
    if 'transport input' in cmd and 'telnet' in cmd:
        return {
            "level": "danger",
            "title": "Telnet 원격 접속 허용",
            "reason": "평문 전송 프로토콜인 Telnet 접속이 허용되어 계정 및 패스워드 스니핑 위험이 있습니다."
        }
    if cmd in ('ip http server', 'service telnet'):
        return {
            "level": "danger",
            "title": "비보안 서비스 활성화",
            "reason": "암호화되지 않은 HTTP 웹 또는 Telnet 서비스가 가동 중입니다."
        }

    # 1-4. 보안 기능 명시적 비활성화 (no ...)
    if cmd in ('no switchport port-security', 'no ip verify source', 'no ip dhcp snooping'):
        return {
            "level": "danger",
            "title": "보안 보호 기능 무력화",
            "reason": "포트 시큐리티 또는 소스 가드 등 L2/L3 보안 방어 기능이 'no'로 해제되어 있습니다."
        }
    if cmd == 'no service password-encryption':
        return {
            "level": "danger",
            "title": "패스워드 암호화 비활성화",
            "reason": "로컬 패스워드가 설정 파일에 평문으로 노출될 수 있습니다."
        }

    # 1-5. 광범위한 ACL Any Any 허용
    if re.search(r'\bpermit\s+(ip|tcp|udp)\s+any\s+any\b', cmd) or cmd == 'permit any any':
        return {
            "level": "danger",
            "title": "전면 허용 (Permit Any Any) ACL",
            "reason": "모든 송수신 트래픽을 필터링 없이 허용하여 방화벽/ACL 정책이 우회됩니다."
        }

    # 2. WARNING (불필요 설정 또는 라우팅 변경 주의)
    if re.search(r'^(router\s+|ip route\s+|ipv6 route\s+)', cmd) or (p_norm.startswith('router ') and cmd.startswith('neighbor ')):
        return {
            "level": "warning",
            "title": "비인가 라우팅 / 정적 경로 추가",
            "reason": "골든 템플릿에 없는 라우팅 프로토콜 또는 정적 경로가 추가되어 트래픽 경로 왜곡이나 루프가 발생할 수 있습니다."
        }
    if cmd.startswith('username ') or cmd.startswith('enable '):
        return {
            "level": "warning",
            "title": "미승인 인증/계정 설정",
            "reason": "표준 골든 템플릿에 등록되지 않은 추가 로컬 사용자 또는 인증 설정입니다."
        }
    if p_norm.startswith('interface ') and any(cmd.startswith(p) for p in ('ip address', 'standby ', 'vrrp ', 'ip helper-address')):
        return {
            "level": "warning",
            "title": "인터페이스 IP / 이중화 설정 변경",
            "reason": "인터페이스에 게이트웨이 또는 IP 주소가 비표준으로 추가 설정되어 있습니다."
        }
    if cmd in ('service config', 'ip finger', 'ip bootp server', 'ip tftp server'):
        return {
            "level": "warning",
            "title": "불필요 레거시 서비스 활성화",
            "reason": "공격 표면을 넓히는 불필요한 네트워크 서비스가 동작 중입니다."
        }

    # 3. INFO (일반 추가 항목)
    return {
        "level": "info",
        "title": "미인가 추가 설정",
        "reason": "골든 템플릿에 정의되지 않은 설정 항목입니다."
    }


def generate_rollback_command(command_line: str, parent_node: str = "") -> tuple[str, str]:
    """
    단일 추가 설정에 대한 Cisco CLI 롤백 명령어 및 세션 블록 반환.
    반환값: (single_rollback_line, session_block)
    """
    cmd = command_line.strip()
    p = parent_node.strip()

    # 이미 'no '로 시작하는 경우 -> 'no'를 제거하여 원상 복구
    if cmd.lower().startswith('no '):
        clean_restore = cmd[3:].strip()
        if p:
            return clean_restore, f"{p}\n {clean_restore}"
        return clean_restore, clean_restore

    # 특수 롤백 변환 규칙
    cmd_lower = cmd.lower()

    if p:
        # 부모가 있는 자식 명령어 롤백
        if cmd_lower.startswith('ip address '):
            rb = "no ip address"
        elif cmd_lower.startswith('ipv6 address '):
            rb = "no ipv6 address"
        elif cmd_lower.startswith('description '):
            rb = "no description"
        elif cmd_lower.startswith('switchport trunk allowed vlan add '):
            # vlan add 10 -> vlan remove 10
            vlan_part = cmd[len('switchport trunk allowed vlan add '):].strip()
            rb = f"switchport trunk allowed vlan remove {vlan_part}"
        elif cmd_lower.startswith('switchport access vlan '):
            rb = "no switchport access vlan"
        elif cmd_lower.startswith('switchport voice vlan '):
            rb = "no switchport voice vlan"
        elif cmd_lower.startswith('standby ') and ' ip ' in cmd_lower:
            parts = cmd.split()
            rb = f"no standby {parts[1]}" if len(parts) >= 2 else "no standby"
        elif cmd_lower == 'shutdown':
            rb = "no shutdown"
        else:
            rb = f"no {cmd}"

        session = f"{p}\n {rb}"
        return rb, session

    # 글로벌 명령어 롤백
    if cmd_lower.startswith('username '):
        parts = cmd.split()
        uname = parts[1] if len(parts) >= 2 else ""
        rb = f"no username {uname}" if uname else f"no {cmd}"
    elif cmd_lower.startswith('snmp-server community '):
        parts = cmd.split()
        comm = parts[2] if len(parts) >= 3 else ""
        rb = f"no snmp-server community {comm}" if comm else f"no {cmd}"
    elif cmd_lower.startswith('ip route ') or cmd_lower.startswith('ipv6 route '):
        rb = f"no {cmd}"
    elif cmd_lower.startswith('interface '):
        # 인터페이스 블록 전체가 추가된 경우: 초기화 및 shutdown
        rb = f"default {cmd}"
        session = f"default {cmd}\n{cmd}\n shutdown"
        return rb, session
    elif cmd_lower.startswith('router ') or cmd_lower.startswith('vrf definition ') or cmd_lower.startswith('ip vrf ') or cmd_lower.startswith('vlan '):
        rb = f"no {cmd}"
    elif cmd_lower.startswith('ip access-list '):
        rb = f"no {cmd}"
    else:
        rb = f"no {cmd}"

    return rb, rb


def build_rollback_script(extra_items: list[dict], hostname: str = "Device") -> str:
    """
    모든 추가 설정을 제거하기 위한 표준 Cisco CLI 롤백 스크립트 전문 생성.
    블록 전체가 추가된 경우는 최상위 no 명령으로 깔끔하게 처리하고,
    블록 내 일부 라인만 추가된 경우는 해당 블록에 진입하여 개별 라인을 제거.
    """
    if not extra_items:
        return "! No extra configurations detected. Config is 100% clean."

    globals_list = []
    entire_blocks_to_remove = {}  # norm_p -> block_rollback_cmd
    parents_map = {}              # norm_p -> (parent_display, [child_rollback_cmds])

    for it in extra_items:
        p = (it.get("parent_node") or "").strip()
        is_block_extra = it.get("is_block_extra", False)
        rb_cmd = it.get("rollback_cmd", "")
        if not rb_cmd:
            rb_cmd, _ = generate_rollback_command(it.get("command_line", ""), p)

        if p:
            norm_p = _normalize_parent(p)
            if is_block_extra:
                # 블록 전체가 미인가인 경우 부모 레벨에서 통째로 제거
                blk_rb = it.get("block_rollback") or f"no {p}"
                if norm_p not in entire_blocks_to_remove:
                    entire_blocks_to_remove[norm_p] = blk_rb
            else:
                if norm_p not in parents_map:
                    parents_map[norm_p] = (p, [])
                if rb_cmd not in parents_map[norm_p][1]:
                    parents_map[norm_p][1].append(rb_cmd)
        else:
            if rb_cmd not in globals_list:
                globals_list.append(rb_cmd)

    lines = [
        "! " + "=" * 65,
        f"! Rollback Script for {hostname}",
        "! Generated automatically by Network Config Auditor",
        f"! Total extra/unmanaged configurations to remove: {len(extra_items)} item(s)",
        "! " + "=" * 65,
        "configure terminal",
        "!"
    ]

    if globals_list:
        lines.append("! [1] 글로벌 불필요/보안 위협 설정 제거")
        for g in globals_list:
            lines.append(g)
        lines.append("!")

    if entire_blocks_to_remove:
        lines.append("! [2] 비인가 추가 블록 전체 제거")
        for norm_p, blk_cmd in entire_blocks_to_remove.items():
            lines.append(blk_cmd)
        lines.append("!")

    if parents_map:
        lines.append("! [3] 기존 블록/인터페이스 내 불필요 하위 설정 제거")
        for norm_p, (p_disp, cmds) in parents_map.items():
            lines.append(p_disp)
            for c in cmds:
                lines.append(f" {c}")
            lines.append(" exit")
            lines.append("!")

    lines.append("end")
    lines.append("! 설정 저장 권고: write memory")
    return "\n".join(lines)


def generate_clean_config(pure_config: str, extra_items: list[dict]) -> str:
    """
    타겟 설정 원본에서 감지된 extra 라인들을 주석 처리하거나 제거한 정제된 Clean Config 생성.
    """
    if not pure_config or not extra_items:
        return pure_config

    extra_lines_set = set()
    for it in extra_items:
        cmd = (it.get("command_line") or "").strip().lower()
        if cmd:
            extra_lines_set.add(cmd)

    clean_lines = []
    for line in pure_config.splitlines():
        s = line.strip().lower()
        if s in extra_lines_set:
            clean_lines.append(f"! [REMOVED_BY_AUDITOR] {line.strip()}")
        else:
            clean_lines.append(line)

    return "\n".join(clean_lines)


def detect_extra_configs(
    target_parsed: dict,
    golden_items: list[dict],
    golden_parsed: dict = None,
    matched_target_ids: set = None
) -> list[dict]:
    """
    골든 템플릿(점검 룰 + 골든 원본 설정)과 비교하여 타겟 장비에 '추가된(Extra/Unmanaged)' 설정을 감지.
    준수율 100%인 경우에도 점검하지 않는 항목 중 추가된 설정을 정확히 찾아냄.
    """
    if matched_target_ids is None:
        matched_target_ids = set()

    # 1. 골든 승인 집합 구축 (골든 템플릿 점검 항목 + 골든 원본 파싱 블록)
    golden_approved_globals = set()
    golden_approved_parents = {}    # norm_p -> set of norm_cmd
    golden_approved_blocks = set()

    # 1-1. golden_items 수집
    for it in golden_items:
        p = _normalize_parent(it.get("parent_node") or "")
        c = _normalize_cmd_line(it.get("command_line") or it.get("label") or "")
        if " > " in c and not it.get("command_line"):
            c = _normalize_cmd_line(c.split(" > ")[-1])

        if p:
            if p not in golden_approved_parents:
                golden_approved_parents[p] = set()
            golden_approved_parents[p].add(c)
            golden_approved_blocks.add(p)
        elif c:
            golden_approved_globals.add(c)

    # 1-2. golden_parsed 수집 (골든 템플릿 원본에 있었던 모든 라인)
    if golden_parsed and isinstance(golden_parsed, dict):
        for b in golden_parsed.get("blocks", []):
            for it in b.get("items", []):
                p = _normalize_parent(it.get("parent_node") or "")
                c = _normalize_cmd_line(it.get("command_line") or it.get("label") or "")
                if " > " in c and not it.get("command_line"):
                    c = _normalize_cmd_line(c.split(" > ")[-1])

                if p:
                    if p not in golden_approved_parents:
                        golden_approved_parents[p] = set()
                    golden_approved_parents[p].add(c)
                    golden_approved_blocks.add(p)
                elif c:
                    golden_approved_globals.add(c)

    # 무시할 시스템 기본 라인
    ignored_prefixes = ('hostname ', 'version ', 'end', '!', 'building configuration', 'current configuration')

    extra_items = []
    target_blocks = target_parsed.get("blocks", [])

    for b in target_blocks:
        bid = b.get("block_id", "")
        for it in b.get("items", []):
            it_id = it.get("id", "")
            p_orig = (it.get("parent_node") or "").strip()
            c_orig = (it.get("command_line") or it.get("label") or "").strip()
            if " > " in c_orig and not it.get("command_line"):
                c_orig = c_orig.split(" > ")[-1].strip()

            c_norm = _normalize_cmd_line(c_orig)
            p_norm = _normalize_parent(p_orig)

            # 무시할 라인
            if not c_norm or any(c_norm.startswith(pfx) for pfx in ignored_prefixes):
                continue

            # 이미 골든 룰 매칭에 사용된 타겟 아이템이면 승인된 것이므로 패스
            if it_id in matched_target_ids:
                continue

            is_extra = False
            is_block_extra = False
            block_rollback = ""

            if p_norm:
                # 부모 블록이 있는 경우
                # (1) 부모 블록 자체가 골든에 없는 경우
                if p_norm not in golden_approved_parents and p_norm not in golden_approved_blocks:
                    is_extra = True
                    is_block_extra = True
                    if p_norm.startswith('interface '):
                        block_rollback = f"default {p_orig}\n{p_orig}\n shutdown"
                    else:
                        block_rollback = f"no {p_orig}"
                else:
                    # (2) 부모는 골든에 있지만, 자식 명령어가 골든에 없는 경우
                    approved_children = golden_approved_parents.get(p_norm, set())
                    matched_in_golden = False
                    for ac in approved_children:
                        if _is_same_normalized(ac, c_norm) or ac in c_norm:
                            matched_in_golden = True
                            break
                    if not matched_in_golden:
                        is_extra = True
            else:
                # 글로벌 명령어인 경우
                matched_in_golden = False
                for ag in golden_approved_globals:
                    if _is_same_normalized(ag, c_norm) or ag in c_norm:
                        matched_in_golden = True
                        break
                if not matched_in_golden:
                    is_extra = True

            if is_extra:
                # 위험도 분석 및 롤백 명령어 산출
                risk_info = classify_risk(c_orig, p_orig)
                rb_cmd, rb_session = generate_rollback_command(c_orig, p_orig)

                extra_items.append({
                    "id": it_id,
                    "section": it.get("section", bid),
                    "parent_node": p_orig,
                    "command_line": c_orig,
                    "raw_block": it.get("raw_block", c_orig),
                    "risk": risk_info["level"],         # 'danger', 'warning', 'info'
                    "risk_title": risk_info["title"],
                    "risk_reason": risk_info["reason"],
                    "is_block_extra": is_block_extra,
                    "block_rollback": block_rollback,
                    "rollback_cmd": rb_cmd,
                    "rollback_session": rb_session,
                })

    return extra_items



# ════════════════════════════════════════════════════════════════════════
# 인터페이스 정책 프로파일 (Interface Policy Profiles) 평가 엔진
# ════════════════════════════════════════════════════════════════════════

def _evaluate_intf_condition(match_type: str, pattern: str, actual: str) -> bool:
    """인터페이스 이름 또는 Description 조건 판정 (exact, contains, regex, exists, none)."""
    mtype = (match_type or "").lower().strip()
    act = (actual or "").strip()
    pat = (pattern or "").strip()

    if mtype in ("none", ""):
        return True
    if mtype == "exists":
        return bool(act)
    if not act:
        return False
    if mtype == "exact":
        return _is_same_normalized(pat, act)
    if mtype == "contains":
        return pat.lower() in act.lower()
    if mtype == "regex":
        try:
            return bool(re.search(pat, act, re.I))
        except re.error:
            return False
    return False


def match_interface_profile(
    intf_name: str,
    desc_text: str,
    is_l2: bool,
    profiles: list[dict]
) -> tuple[dict | None, int]:
    """
    인터페이스의 이름, description, L2/L3 타입을 기준으로
    등록된 interface_profiles 중 가장 적합한 프로파일을 매칭하고 우선순위 점수를 반환합니다.
    """
    if not profiles:
        return None, 0

    best_profile = None
    best_score = -1

    for prof in profiles:
        target_type = prof.get("target_type", "any").lower()
        if target_type == "l2" and not is_l2:
            continue
        if target_type == "l3" and is_l2:
            continue

        # 1. Name Condition
        name_cond = prof.get("name_condition", {})
        name_mtype = name_cond.get("match_type", "exists")
        name_pat = name_cond.get("pattern", "")
        if not _evaluate_intf_condition(name_mtype, name_pat, intf_name):
            continue

        # 2. Description Condition
        desc_cond = prof.get("desc_condition", {})
        desc_mtype = desc_cond.get("match_type", "none")
        desc_pat = desc_cond.get("pattern", "")
        if not _evaluate_intf_condition(desc_mtype, desc_pat, desc_text):
            continue

        # 3. 우선순위 점수 (Specificity Score) 계산
        has_specific_desc = desc_mtype in ("exact", "contains", "regex") and bool(desc_pat)
        has_specific_name = name_mtype in ("exact", "contains", "regex") and bool(name_pat)

        if has_specific_desc and has_specific_name:
            score = 40
        elif has_specific_desc:
            score = 30
        elif has_specific_name:
            score = 20
        else:
            score = 10

        if score > best_score:
            best_score = score
            best_profile = prof

    return best_profile, best_score


def _extract_target_interfaces(target_parsed: dict, inventory: dict) -> list[dict]:
    """타겟 설정에서 모든 L2/L3 인터페이스 블록 정보를 추출합니다."""
    interfaces = []
    blocks = target_parsed.get("blocks", [])
    seen_parents = set()

    for b in blocks:
        bid = b.get("block_id", "")
        if bid not in ("interfaces_l2", "interfaces_l3"):
            continue
        is_l2 = (bid == "interfaces_l2")
        for it in b.get("items", []):
            p = (it.get("parent_node") or "").strip()
            if not p or p in seen_parents:
                continue
            seen_parents.add(p)

            norm_p = _normalize_parent(p)
            children = inventory["parents"].get(norm_p, [])

            # Description 추출
            desc_text = ""
            for c in children:
                line_str = c.get("line", "").strip()
                if line_str.lower().startswith("description "):
                    desc_text = line_str[12:].strip()
                    break

            intf_name = p.split()[-1] if len(p.split()) > 1 else p
            interfaces.append({
                "parent_node": p,
                "normalized_parent": norm_p,
                "intf_name": intf_name,
                "is_l2": is_l2,
                "desc_text": desc_text,
                "children": children
            })
    return interfaces


# ════════════════════════════════════════════════════════════════════════
# 메인 COMPARE 함수
# ════════════════════════════════════════════════════════════════════════

def compare(
    golden_items: list[dict],
    target_parsed: dict,
    conditional_rules: list[dict] = None,
    golden_parsed: dict = None,
    interface_profiles: list[dict] = None
) -> dict:
    """
    골든 템플릿 항목 + 인터페이스 프로파일 + 조건부 규칙 vs 타겟 파싱 결과 비교.
    추가로 타겟 장비에 추가된 불필요/보안 위협 설정(Extra Configs)의 Diff 및 롤백 스크립트 산출.
    """
    item_results = []
    has_fail = False
    has_review = False
    matched_target_ids = set()

    hostname = target_parsed.get("hostname", "")
    all_challenge_items = list(golden_items)

    # 1. 호스트명 기반 조건부 규칙 적용
    if conditional_rules and hostname:
        for rule in conditional_rules:
            regex = rule.get("hostname_regex", "")
            try:
                if re.search(regex, hostname, re.I):
                    extra_items = rule.get("items", [])
                    for i in extra_items:
                        i["is_conditional"] = True
                        i["condition_regex"] = regex
                        all_challenge_items.append(i)
            except re.error:
                continue

    target_sections = target_parsed.get("sections", {})
    # 타겟 인벤토리 생성 (부모별/글로벌별 고속 지능형 인덱스)
    inventory = _extract_target_inventory(target_parsed)

    # 2. 골든 룰 항목 매칭 및 평가 (기본 글로벌 및 명시적 룰)
    for item in all_challenge_items:
        item_id = item["id"]
        section = item["section"]
        match_type = item.get("match_type", "exact")
        expected = item.get("expected_value", "")
        if expected is None or expected == "":
            expected = item.get("value", "")

        label = item.get("label", item_id)
        weight = item.get("weight", "required")
        is_cond = item.get("is_conditional", False)

        # 지능형 타겟 설정 검색
        actual_value, found_context, matched_id = _find_target_actual(item, inventory, target_sections)
        if matched_id:
            matched_target_ids.add(matched_id)

        # 비교 대상 값 결정
        if item.get("full_line_mode"):
            cmp_target = found_context if found_context else actual_value
        else:
            cmp_target = actual_value if actual_value is not None else (found_context if found_context else None)

        # 값 및 match_type 기반 판정
        matched, display_actual = _match_value(expected, cmp_target, match_type, section)

        if matched and found_context and not display_actual.startswith("("):
            display_actual = found_context

        if matched:
            status = "pass"
            message = "OK"
        else:
            if weight == "required":
                status = "fail"
                has_fail = True
                message = f"불일치 (기대: {expected})"
            else:
                status = "review"
                has_review = True
                message = f"리뷰 권고 (기대: {expected})"

        item_results.append({
            "id": item_id,
            "label": label + (" (조건부)" if is_cond else ""),
            "section": section,
            "match_type": match_type,
            "weight": weight,
            "status": status,
            "expected": str(expected),
            "actual": display_actual,
            "message": message,
            "is_conditional": is_cond,
            "condition_regex": item.get("condition_regex")
        })

    # 3. 인터페이스 정책 프로파일(Interface Profiles) 평가
    if interface_profiles:
        target_interfaces = _extract_target_interfaces(target_parsed, inventory)
        # 이미 golden_items에 직접 명시된 고정 인터페이스 부모 노드 목록 수집
        explicit_parents = {
            _normalize_parent(it.get("parent_node", ""))
            for it in golden_items
            if it.get("parent_node")
        }

        for intf in target_interfaces:
            # 명시적으로 개별 룰이 지정된 포트는 고정 룰을 우선 존중
            if intf["normalized_parent"] in explicit_parents:
                continue

            prof, score = match_interface_profile(
                intf_name=intf["intf_name"],
                desc_text=intf["desc_text"],
                is_l2=intf["is_l2"],
                profiles=interface_profiles
            )
            if not prof:
                continue

            prof_name = prof.get("name", "인터페이스 정책")
            prof_rules = prof.get("rules", [])

            for p_rule in prof_rules:
                cmd = p_rule.get("command", "").strip()
                if not cmd:
                    continue
                match_type = p_rule.get("match_type", "exact")
                weight = p_rule.get("weight", "required")
                expected = p_rule.get("expected_value") or cmd

                # 해당 인터페이스의 하위 라인에서 일치 여부 검색
                matched = False
                matched_line = ""
                matched_id = ""

                for child in intf["children"]:
                    cline = child.get("line", "").strip()
                    cid = child.get("id", "")

                    if match_type == "exact":
                        if _is_same_normalized(cmd, cline):
                            matched = True
                            matched_line = cline
                            matched_id = cid
                            break
                    elif match_type == "contains":
                        if cmd.lower() in cline.lower():
                            matched = True
                            matched_line = cline
                            matched_id = cid
                            break
                    elif match_type == "regex":
                        try:
                            if re.search(cmd, cline, re.I):
                                matched = True
                                matched_line = cline
                                matched_id = cid
                                break
                        except re.error:
                            pass
                    elif match_type == "exists":
                        if cline.lower().startswith(cmd.lower()):
                            matched = True
                            matched_line = cline
                            matched_id = cid
                            break

                if matched:
                    if matched_id:
                        matched_target_ids.add(matched_id)
                    status = "pass"
                    message = "OK"
                    display_actual = matched_line
                else:
                    if weight == "required":
                        status = "fail"
                        has_fail = True
                        message = f"불일치 (기대: {expected})"
                    else:
                        status = "review"
                        has_review = True
                        message = f"리뷰 권고 (기대: {expected})"
                    display_actual = "(미존재)"

                clean_cmd_id = re.sub(r'[^a-zA-Z0-9_]', '_', cmd)
                clean_intf_id = re.sub(r'[^a-zA-Z0-9_]', '_', intf["intf_name"])

                item_results.append({
                    "id": f"prof.{prof.get('id', 'p')}.{clean_intf_id}.{clean_cmd_id}",
                    "label": f"interface {intf['intf_name']} > {cmd}",
                    "section": f"interface ({intf['intf_name']})",
                    "match_type": match_type,
                    "weight": weight,
                    "status": status,
                    "expected": str(expected),
                    "actual": display_actual,
                    "message": message,
                    "is_profile_rule": True,
                    "profile_id": prof.get("id", ""),
                    "profile_name": prof_name,
                    "parent_node": intf["parent_node"]
                })

    # 전체 골든 룰 판정
    if has_fail:
        overall = "Fail"
    elif has_review:
        overall = "Review"
    else:
        overall = "Pass"

    total = len(item_results)
    passed = sum(1 for r in item_results if r["status"] == "pass")
    score = round((passed / total * 100) if total > 0 else 100.0, 1)

    # 3. 추가된 불필요/보안 위협 설정(Diff: Extra Configs) 탐지
    extra_configs = detect_extra_configs(
        target_parsed=target_parsed,
        golden_items=golden_items,
        golden_parsed=golden_parsed,
        matched_target_ids=matched_target_ids
    )

    danger_count = sum(1 for ec in extra_configs if ec["risk"] == "danger")
    warning_count = sum(1 for ec in extra_configs if ec["risk"] == "warning")
    info_count = sum(1 for ec in extra_configs if ec["risk"] == "info")

    # 4. 롤백 CLI 전문 스크립트 및 정제된 Clean Config 생성
    rollback_script = build_rollback_script(extra_configs, hostname=hostname)
    pure_config = target_parsed.get("pure_config", "")
    clean_config = generate_clean_config(pure_config, extra_configs)

    return {
        "overall": overall,
        "score": score,
        "total_items": total,
        "passed_items": passed,
        "items": item_results,
        "extra_configs": extra_configs,
        "extra_count": len(extra_configs),
        "extra_summary": {
            "total": len(extra_configs),
            "danger": danger_count,
            "warning": warning_count,
            "info": info_count,
        },
        "rollback_script": rollback_script,
        "clean_config": clean_config
    }


def match_template(hostname: str, templates: list[dict]) -> dict | None:
    """
    hostname에 대해 템플릿 목록에서 regex 매칭되는 첫 번째 템플릿 반환.
    """
    if not hostname:
        return None
    for tpl in templates:
        pattern = tpl.get("hostname_regex", "")
        if not pattern:
            continue
        try:
            if re.match(pattern, hostname):
                return tpl
        except re.error:
            continue
    return None
