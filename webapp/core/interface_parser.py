"""
core/interface_parser.py
인터페이스 전용 설정 파서.

- 블록 파싱: 인터페이스 이름 + 들여쓰기된 모든 하위 옵션을 하나의 블록으로 수집
- 인터페이스 분류: Uplink (L3, 물리적 업링크) vs L2 (Access/Trunk 포트)
- 비교 시 로직:
  * Uplink: 인터페이스 이름(번호) + 옵션 모두 중요 (IP 제외 선택 가능)
  * L2: 인터페이스 이름 무관 → 옵션 set 기준 비교
"""

import re
from typing import List, Dict, Any


# ── 인터페이스 타입 분류 ─────────────────────────────────────────────

# 업링크 / L3 인터페이스 패턴
L3_PATTERNS = re.compile(
    r'^(Vlan|Loopback|Tunnel|BDI|Dialer|Async|NVI|Port-channel'
    r'|GigabitEthernet|TenGigabitEthernet|HundredGigE|FortyGigabitEthernet'
    r'|TwentyFiveGigE|mgmt|Management'
    r'|Ethernet[0-9])',
    re.I
)

# L2 전용 패턴 (업링크일 수도 있지만 trunk/access 옵션에 따라 분류)
# description, switchport, channel-group 등 옵션으로 판단

IP_COMMAND_RE = re.compile(r'^\s*ip address\s+', re.I)
SWITCHPORT_RE = re.compile(r'^\s*switchport\s+', re.I)
CHANNEL_GROUP_RE = re.compile(r'^\s*channel-group\s+', re.I)
VLAN_RE = re.compile(r'^\s*(vlan|access vlan|trunk allowed vlan)\s+', re.I)
STP_RE = re.compile(r'^\s*spanning-tree\s+', re.I)
LOGGING_PORT_RE = re.compile(r'^\s*logging event port', re.I)


def parse_interfaces(config_text: str) -> List[Dict[str, Any]]:
    """
    설정 텍스트를 파싱하여 인터페이스 블록 목록을 반환.
    각 블록은 인터페이스 이름과 모든 하위 옵션을 포함.
    """
    interfaces = []
    current_intf = None
    current_options = []

    def flush():
        nonlocal current_intf, current_options
        if current_intf:
            block_text = "\n".join([current_intf] + [f"  {o}" for o in current_options])
            intf_type = classify_interface(current_intf, current_options)
            intf_name = current_intf.split(None, 1)[1] if len(current_intf.split()) > 1 else current_intf
            interfaces.append({
                "name": intf_name,
                "header": current_intf,
                "options": list(current_options),
                "block_text": block_text,
                "type": intf_type,        # 'uplink' | 'l2'
                "has_ip": any(IP_COMMAND_RE.match(o) for o in current_options),
                "has_switchport": any(SWITCHPORT_RE.match(o) for o in current_options),
            })
        current_intf = None
        current_options = []

    for raw_line in config_text.splitlines():
        # 빈 줄은 별도 처리 — 설정 블록 내 빈 줄은 들여쓰기 있는 것으로 취급
        if raw_line.strip() == '':
            if current_intf is not None:
                continue   # 인터페이스 블록 내부의 빈 줄 -> 무시하고 계속
            continue

        is_indented = raw_line.startswith((' ', '\t'))
        stripped = raw_line.strip()

        if not is_indented:
            # 새로운 최상위 명령어 시작
            if stripped.lower().startswith('interface '):
                flush()
                current_intf = stripped
                current_options = []
            else:
                # interface 블록 종료
                flush()
        else:
            # 들여쓰기 있는 라인 → 현재 인터페이스 속성
            if current_intf is not None and stripped:
                current_options.append(stripped)

    flush()
    return interfaces


def classify_interface(header: str, options: List[str]) -> str:
    """
    인터페이스를 'uplink'(L3/업링크) 또는 'l2'(L2 포트)로 분류.
    
    분류 기준:
    - Vlan / Loopback / Tunnel / BDI 등 논리 인터페이스 → uplink
    - ip address가 있으면 → uplink
    - switchport가 있는 경우 → l2
    - 물리 인터페이스 중 channel-group + trunk → 어느 쪽이든 옵션 확인
    """
    header_lower = header.lower()
    name_part = header.split(None, 1)[1] if len(header.split()) > 1 else ''

    # 논리 인터페이스는 무조건 uplink
    logical = re.match(r'^(Vlan|Loopback|Tunnel|BDI|Dialer|NVI|mgmt|management)', name_part, re.I)
    if logical:
        return 'uplink'

    has_ip = any(IP_COMMAND_RE.match(o) for o in options)
    has_switchport = any(SWITCHPORT_RE.match(o) for o in options)

    if has_ip and not has_switchport:
        return 'uplink'
    if has_switchport:
        return 'l2'

    # Port-channel 또는 물리 인터페이스기인데 switchport, ip 둘 다 없는 경우
    # → 업링크로 분류 (routed port 가능성)
    return 'uplink'


def flatten_interfaces_for_ui(interfaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    인터페이스 목록을 UI 비교 항목(golden_items) 형태로 변환.

    업링크 vs L2에 따라 비교 방식을 다르게 설정:
    - uplink: match_type='exact', parent_header=인터페이스명, IP 설정은 match_type='exists'로
    - l2:     match_type='contains', parent_header 없음(=옵션 값 기반 비교)
    """
    items = []
    for intf in interfaces:
        intf_type = intf["type"]
        name = intf["name"]
        options = intf["options"]

        if intf_type == 'uplink':
            # 업링크: 인터페이스 이름(header) + 개별 옵션 모두 항목화
            for j, opt in enumerate(options):
                opt_stripped = opt.strip()
                if not opt_stripped:
                    continue
                is_ip = bool(IP_COMMAND_RE.match(opt_stripped))
                items.append({
                    "id": f"interface.uplink.{name}.opt.{j}",
                    "section": "interface (uplink)",
                    "label": opt_stripped,
                    "value": opt_stripped,
                    "source": "raw",
                    "raw_block": intf["block_text"],
                    "parent_header": f"interface {name}",
                    "match_type": "exists" if is_ip else "exact",
                    "weight": "optional" if is_ip else "required",
                    "intf_type": "uplink",
                    "intf_name": name,
                })
        else:  # l2
            # L2: 인터페이스 이름 무관 → 옵션(설정 내용) 기준 비교
            # 같은 옵션 set을 가진 인터페이스를 찾는 방식
            for j, opt in enumerate(options):
                opt_stripped = opt.strip()
                if not opt_stripped:
                    continue
                items.append({
                    "id": f"interface.l2.{name}.opt.{j}",
                    "section": "interface (L2)",
                    "label": opt_stripped,
                    "value": opt_stripped,
                    "source": "raw",
                    "raw_block": intf["block_text"],
                    "parent_header": f"interface {name}",   # 저장용 참고 정보
                    "match_type": "contains",
                    "weight": "required",
                    "intf_type": "l2",
                    "intf_name": name,                     # 비교 시 무시됨
                })

    return items
