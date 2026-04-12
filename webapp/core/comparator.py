"""
core/comparator.py
골든 템플릿 항목과 타겟 설정을 비교하여 Pass / Review / Fail 결과 생성.
"""

import re
from typing import Any


def _match_value(expected: Any, actual: Any, match_type: str) -> bool:
    """단일 값 비교."""
    if match_type == "exists":
        return actual not in (None, "", [], {})
    if match_type == "exact":
        exp_str = str(expected).strip()
        act_str = str(actual).strip()
        if exp_str == act_str:
            return True
        if '\n' in act_str:
            for line in act_str.splitlines():
                if exp_str == line.strip():
                    return True
        return False
    if match_type == "regex":
        try:
            return bool(re.search(str(expected), str(actual)))
        except re.error:
            return False
    if match_type == "contains":
        return str(expected) in str(actual)
    return str(expected) == str(actual)


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
                if re.search(regex, hostname):
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
        elif source == "raw" and "raw" in target_entry:
            parent_hdr = item.get("parent_header")
            if parent_hdr:
                target_block = None
                for block in target_entry["raw"]:
                    if block.startswith(parent_hdr):
                        target_block = block
                        break
                actual_value = target_block
            else:
                actual_value = '\n'.join(target_entry["raw"])

        matched = _match_value(expected, actual_value, match_type)

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
            "actual": str(actual_value) if actual_value is not None else "(없음)",
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
