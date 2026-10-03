"""
core/comparator.py
골든 템플릿 항목과 타겟 설정을 비교하여 Pass / Review / Fail 결과 생성.
"""

import re
from typing import Any


def _normalize_banner(text: str) -> str:
    """Cisco 배너의 시작/종료 구분자 및 불필요한 공백 제거."""
    if not text:
        return ""
    lines = text.strip().splitlines()
    if not lines:
        return ""
    
    # 첫 줄에서 'banner motd ^C' 또는 'banner login ^C' 등의 명령어 부분 제거 시도
    first_line = lines[0].strip()
    if first_line.lower().startswith('banner '):
        # 'banner motd ' 이후의 구분자 추출 시도
        parts = first_line.split()
        if len(parts) >= 3:
            # 'banner motd ^' -> '^' 이후의 텍스트만 남김
            idx = first_line.find(parts[1]) + len(parts[1])
            content_start = first_line[idx:].lstrip()
            if content_start:
                delim = content_start[0]
                lines[0] = content_start.lstrip(delim).strip()
    
    # 마지막 줄에서 종료 구분자 제거 시도
    if lines:
        last_line = lines[-1].strip()
        if last_line and (len(last_line) == 1 or last_line.endswith('^C')):
             # 보통 구분자 혼자 있거나 ^C 로 끝남
             lines[-1] = last_line.rstrip('^C').strip()
    
    return "\n".join(l.strip() for l in lines if l.strip())


def _is_same_normalized(a: str, b: str) -> bool:
    """공백 종류, 개수, 대소문자 차이를 완전히 무시하고 실질적인 의미가 동일한지 확인."""
    if not a or not b:
        return a == b
    # 모든 종류의 공백(탭, 줄바꿈 등)을 단일 공백으로 치환하여 비교
    norm_a = re.sub(r'[\s\u00A0\t\n\r]+', ' ', str(a).strip()).lower()
    norm_b = re.sub(r'[\s\u00A0\t\n\r]+', ' ', str(b).strip()).lower()
    return norm_a == norm_b


def _match_value(expected: Any, actual_value: Any, match_type: str, section: str = "") -> tuple[bool, str]:
    """
    값 비교 및 UI에 표시할 실제 값(display_actual) 반환.
    """
    exp_str = str(expected).strip()
    act_full = str(actual_value).strip() if actual_value is not None else ""
    
    if not act_full:
        return (False, "(없음)")

    # ── 배너 특수 처리 ──
    if section == "banner":
        norm_exp = _normalize_banner(exp_str)
        norm_act = _normalize_banner(act_full)
        if norm_exp == norm_act or norm_exp in norm_act:
            return (True, "(배너 일치)" if norm_exp == norm_act else "(배너 포함)")
        return (False, act_full.splitlines()[0] + "..." if len(act_full.splitlines()) > 1 else act_full)

    # 줄 단위 분석 전처리
    lines = [l.strip() for l in act_full.splitlines() if l.strip()]
    
    if match_type == "exists":
        # exists: 해당 설정이 대상 파일에 존재하기만 하면 값이 무엇이든 상관없이 합격(Pass)
        if lines:
            return (True, f"(존재함: {lines[0]})")
        elif act_full:
            return (True, f"(존재함: {act_full})")
        return (False, "(미존재)")

    if match_type == "exact":
        # exact: 지정한 기대값과 반드시 정확히 일치해야 합격
        for line in lines:
            if _is_same_normalized(exp_str, line):
                return (True, line)
        if _is_same_normalized(exp_str, act_full):
            return (True, act_full)
        return (False, lines[0] if len(lines) > 0 else "(불일치)")

    if match_type == "regex":
        # regex: ^CE_ 등의 정규표현식 패턴과 일치해야 합격
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
        # contains: *CE1* 형태의 와일드카드 및 단어 포함 검사
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
        # 마지막으로 혹시 모르니 포함 여부 확인 (Fallback)
        if exp_str.lower() in act_full.lower():
            return (True, "(블록 내 포함-F)")

    return (matched, act_full if matched else (lines[0] + "..." if len(lines) > 0 else "(불일치)"))


def _get_nested(data: dict, path: str) -> Any:
    """'a.b.c' 형태의 경로로 중첩 dict에서 값을 추출."""
    keys = path.split('.')
    cur = data
    for k in keys:
        if isinstance(cur, dict):
            cur = cur.get(k)
        elif isinstance(cur, list):
            try:
                cur = cur[int(k)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def compare(golden_items: list[dict], target_parsed: dict, conditional_rules: list[dict] = None) -> dict:
    """
    골든 템플릿 항목 + 조건부 규칙 vs 타겟 파싱 결과 비교.

    conditional_rules: [
      {
        "hostname_regex": "^SH-.*",
        "action": "require",  # "require" (항목 필수), "exclude" (항목 금지)
        "items": [...]        # 추가될 golden_items 형식의 리스트
      }
    ]
    """
    item_results = []
    has_fail = False
    has_review = False

    hostname = target_parsed.get("hostname", "")
    all_challenge_items = list(golden_items)

    # 1. 호스트명 기반 조건부 규칙 적용 (동적 액션)
    if conditional_rules and hostname:
        for rule in conditional_rules:
            regex = rule.get("hostname_regex", "")
            try:
                if re.search(regex, hostname, re.I):
                    # 조건이 일치하면 해당 액션 수행 (여기서는 항목 추가)
                    extra_items = rule.get("items", [])
                    for i in extra_items:
                        i["is_conditional"] = True
                        i["condition_regex"] = regex
                        all_challenge_items.append(i)
            except re.error:
                continue

def _normalize_parent(parent_str: str) -> str:
    """부모 노드 식별자 정규화 (대소문자, 공백, 인터페이스 축약형 보정)."""
    s = re.sub(r'\s+', ' ', str(parent_str).strip().lower())
    # 인터페이스 약어 정규화
    s = re.sub(r'^interface\s+gi(?:gabitethernet)?', 'interface gigabitethernet', s)
    s = re.sub(r'^interface\s+te(?:ngigabitethernet)?', 'interface tengigabitethernet', s)
    s = re.sub(r'^interface\s+lo(?:opback)?', 'interface loopback', s)
    s = re.sub(r'^interface\s+tu(?:nnel)?', 'interface tunnel', s)
    s = re.sub(r'^interface\s+vl(?:an)?', 'interface vlan', s)
    return s


def _extract_target_inventory(target_parsed: dict) -> dict:
    """타겟 설정의 구조화된 계층 인덱스 생성."""
    inventory = {
        "parents": {},        # norm_parent -> list of dict(line, value, raw)
        "globals": [],        # list of dict(line, value, raw)
        "items_by_id": {},    # id -> item
        "all_lines": []       # list of str
    }

    blocks = target_parsed.get("blocks", [])
    for b in blocks:
        for it in b.get("items", []):
            inventory["items_by_id"][it["id"]] = it
            p_node = (it.get("parent_node") or "").strip()
            c_line = (it.get("command_line") or it.get("label") or "").strip()
            if " > " in c_line and not it.get("command_line"):
                c_line = c_line.split(" > ")[-1].strip()
            val = it.get("value", "")

            if p_node:
                norm_p = _normalize_parent(p_node)
                if norm_p not in inventory["parents"]:
                    inventory["parents"][norm_p] = []
                inventory["parents"][norm_p].append({
                    "line": c_line,
                    "value": val,
                    "raw": it.get("raw_block", "")
                })
            else:
                inventory["globals"].append({
                    "line": c_line,
                    "value": val,
                    "raw": it.get("raw_block", "")
                })

    return inventory


def _find_target_actual(item: dict, inventory: dict, target_sections: dict) -> tuple[Any, str]:
    """
    골든 아이템의 parent_node 및 command_line을 바탕으로 타겟 설정에서 실제 설정값을 지능적으로 검색.
    반환값: (actual_value, found_line_context)
    """
    item_id = item.get("id", "")
    section = item.get("section", "")
    p_node = (item.get("parent_node") or "").strip()
    c_line = (item.get("command_line") or item.get("label") or "").strip()
    if " > " in c_line and not item.get("command_line"):
        c_line = c_line.split(" > ")[-1].strip()

    # 1. ID로 직접 일치하는 경우 우선 확인
    if item_id in inventory["items_by_id"]:
        it = inventory["items_by_id"][item_id]
        return it.get("value"), it.get("command_line", c_line)

    # 2. 부모 노드가 있는 경우 (Interface, BGP, OSPF, Line, VRF, ACL 등)
    if p_node:
        norm_p = _normalize_parent(p_node)
        target_children = inventory["parents"].get(norm_p, [])
        if not target_children:
            # 혹시 interface prefix가 생략되었거나 추가된 경우 다시 검색
            for tp_key, tp_list in inventory["parents"].items():
                if tp_key == norm_p or tp_key.endswith(" " + norm_p) or norm_p.endswith(" " + tp_key):
                    target_children = tp_list
                    break

        if target_children:
            # 자식 명령어 중에서 일치하는 항목 탐색
            # 2-1. 명령어 전체가 일치하는 경우 (Exact line match)
            for c in target_children:
                if _is_same_normalized(c["line"], c_line):
                    return c.get("value"), c["line"]

            # 2-2. 명령어 키워드 접두사가 일치하는 경우 (예: 'ip address', 'bgp router-id', 'description')
            cmd_parts = c_line.split()
            if cmd_parts:
                first_word = cmd_parts[0].lower()
                prefix = f"{first_word} {cmd_parts[1].lower()}" if len(cmd_parts) >= 2 else first_word
                for c in target_children:
                    t_line = c["line"].lower()
                    if t_line.startswith(prefix + " ") or t_line == prefix:
                        return c.get("value"), c["line"]

            # 2-3. 네트워크 대역 명령어 (예: 'network 10.46.80.0 mask 255.255.240.0')
            if c_line.lower().startswith("network "):
                for c in target_children:
                    if c["line"].lower().startswith("network "):
                        # 정확한 네트워크 매칭 또는 동일 시작 확인
                        if _is_same_normalized(c["line"], c_line):
                            return c.get("value"), c["line"]

        # 부모는 존재하지 않거나 부모 내에 명령어가 없는 경우
        return None, ""

    # 3. 부모 노드가 없는 글로벌 명령어 (hostname, version, service, ntp 등)
    cmd_parts = c_line.split()
    if cmd_parts:
        first_word = cmd_parts[0].lower()
        prefix = f"{first_word} {cmd_parts[1].lower()}" if len(cmd_parts) >= 2 else first_word
        for g in inventory["globals"]:
            g_line = g["line"]
            if _is_same_normalized(g_line, c_line):
                return g.get("value"), g_line
            if g_line.lower().startswith(prefix + " ") or g_line.lower() == prefix:
                return g.get("value"), g_line
            if g_line.lower().startswith(first_word + " "):
                return g.get("value"), g_line

    # 4. Fallback: 타겟의 raw 섹션 텍스트에서 검색
    target_entry = target_sections.get(section, {})
    if "raw" in target_entry:
        raw_list = target_entry["raw"]
        raw_full = "\n".join(raw_list) if isinstance(raw_list, list) else str(raw_list)
        for line in raw_full.splitlines():
            s_line = line.strip()
            if _is_same_normalized(s_line, c_line):
                return s_line, s_line

    return None, ""


def compare(golden_items: list[dict], target_parsed: dict, conditional_rules: list[dict] = None) -> dict:
    """
    골든 템플릿 항목 + 조건부 규칙 vs 타겟 파싱 결과 비교.
    """
    item_results = []
    has_fail = False
    has_review = False

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
        actual_value, found_context = _find_target_actual(item, inventory, target_sections)

        # 비교 대상 값 결정 (actual_value가 있으면 우선, 없으면 found_context)
        cmp_target = actual_value if actual_value is not None else (found_context if found_context else None)

        # 값 및 match_type 기반 판정
        matched, display_actual = _match_value(expected, cmp_target, match_type, section)

        # 만약 display_actual이 원본 라인 정보가 있으면 더 풍성하게 표시
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

    # 전체 판정
    if has_fail: overall = "Fail"
    elif has_review: overall = "Review"
    else: overall = "Pass"

    total = len(item_results)
    passed = sum(1 for r in item_results if r["status"] == "pass")
    score = round((passed / total * 100) if total > 0 else 100.0, 1)

    return {
        "overall": overall,
        "score": score,
        "total_items": total,
        "passed_items": passed,
        "items": item_results,
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
