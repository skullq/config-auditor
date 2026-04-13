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
        if exp_str:
            for line in lines:
                if _is_same_normalized(exp_str, line) or (exp_str.lower() in line.lower()):
                    return (True, line)
            return (False, "(미발견)")
        return (True, "(존재함)")

    if match_type == "exact":
        for line in lines:
            if _is_same_normalized(exp_str, line):
                return (True, line)
        if _is_same_normalized(exp_str, act_full):
            return (True, act_full)
        return (False, lines[0] + "..." if len(lines) > 0 else "(불일치)")

    if match_type == "regex":
        try:
            pattern = re.compile(exp_str, re.I)
            for line in lines:
                if pattern.search(line):
                    return (True, line)
            if pattern.search(act_full):
                return (True, "(전체 매칭됨)")
            return (False, "(미일치)")
        except re.error:
            return (False, "(Regex 에러)")

    if match_type == "contains":
        low_exp = exp_str.lower()
        for line in lines:
            if low_exp in line.lower() or _is_same_normalized(exp_str, line):
                return (True, line)
        if low_exp in act_full.lower():
            return (True, "(블록 내 포함)")
        return (False, lines[0] + "..." if len(lines) > 0 else "(불일치)")

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

    target_sections = target_parsed.get("sections", {})

    for item in all_challenge_items:
        item_id = item["id"]
        section = item["section"]
        match_type = item.get("match_type", "exists")
        expected = item.get("expected_value", "")
        label = item.get("label", item_id)
        weight = item.get("weight", "required")
        source = item.get("source", "genie")
        is_cond = item.get("is_conditional", False)

        # 타겟에서 데이터 추출
        actual_value = None
        target_entry = target_sections.get(section, {})

        if source == "genie" and "genie" in target_entry:
            sub_path = '.'.join(item_id.split('.')[1:])
            actual_value = _get_nested(target_entry["genie"], sub_path)
            matched, display_actual = _match_value(expected, actual_value, match_type, section)
        elif source == "raw" and "raw" in target_entry:
            intf_type = item.get("intf_type")
            parent_hdr = item.get("parent_header")
            
            # 1. L2 인터페이스 특수 처리 (인터페이스 이름 무관)
            if intf_type == "l2":
                found_match = False
                all_l2_actuals = []
                for block in target_entry["raw"]:
                    if "switchport" in block.lower():
                        m, disp = _match_value(expected, block, match_type, section)
                        if m:
                            found_match = True
                            display_actual = disp
                            break
                        all_l2_actuals.append(disp)
                
                matched = found_match
                if not matched:
                    display_actual = "(L2 포트 중 미일치)" if all_l2_actuals else "(L2 포트 없음)"
            
            # 2. 특정 헤더 기반 (Interface, Class-map, Policy-map 등)
            elif parent_hdr:
                target_block = None
                # 1단계: 헤더가 정확히 일치하는 블록 찾기 (startswith 가 아닌 전체 줄 비교)
                for block in target_entry["raw"]:
                    first_line = block.splitlines()[0].strip()
                    if _is_same_normalized(parent_hdr, first_line):
                        target_block = block
                        break
                
                matched, display_actual = _match_value(expected, target_block, match_type, section)
                
                # 2단계: 실패 시 해당 섹션 전체에서 다시 검색 (인터페이스 제외)
                if not matched and section not in ('interface (uplink)', 'interface'):
                    all_raw_text = '\n'.join(target_entry["raw"])
                    m2, d2 = _match_value(expected, all_raw_text, match_type, section)
                    if m2:
                        matched, display_actual = m2, d2
            else:
                all_raw = '\n'.join(target_entry["raw"])
                matched, display_actual = _match_value(expected, all_raw, match_type, section)
        else:
            matched, display_actual = _match_value(expected, None, match_type, section)

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
