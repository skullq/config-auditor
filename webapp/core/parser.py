"""
webapp/core/parser.py
Cisco 설정 파서 엔진 - cisco-config-parser 3.0.0 기반
"""

import re
import os
import json
from typing import Any, Dict, List, Tuple
from cisco_config_parser import ConfigParser
from cisco_config_parser.config_tree import ConfigTree

# -----------------------------------------------------------------------------
# 섹션 분류에 필요한 상수 및 유틸
# -----------------------------------------------------------------------------
TWO_WORD_PREFIXES = {
    'router', 'ip', 'ipv4', 'ipv6', 'crypto', 'no', 'vrf',
    'spanning-tree', 'line', 'snmp-server', 'ntp',
    'logging', 'username', 'boot', 'class-map', 'policy-map',
}

SKIP_RE = re.compile(r'^(Building configuration|Current configuration|Last configuration|!|.*#).*', re.I)


def detect_os(config_text: str) -> str:
    """텍스트 내용을 분석하여 OS 타입을 추정."""
    c_low = config_text.lower()
    if 'show running-config' in c_low:
        if 'ios-xe' in c_low:
            return 'iosxe'
        if 'ios-xr' in c_low:
            return 'iosxr'
    if 'nx-os' in c_low or 'feature ' in c_low:
        return 'nxos'
    if 'ios-xr' in c_low or 'prefix-set' in c_low:
        return 'iosxr'
    if 'aireos' in c_low:
        return 'aireos'
    return 'iosxe'  # 기본값


def detect_platform(config_text: str, os_hint: str = 'auto') -> str:
    """cisco-config-parser가 지원하는 platform (IOS, NXOS, XR) 식별."""
    h = str(os_hint).lower()
    if 'nx' in h:
        return 'NXOS'
    if 'xr' in h:
        return 'XR'
    if 'ios' in h:
        return 'IOS'

    try:
        p = ConfigParser(config_text)
        return p.determine_platform()
    except Exception:
        c_low = config_text.lower()
        if 'nx-os' in c_low or 'feature ' in c_low:
            return 'NXOS'
        if 'ios-xr' in c_low or 'prefix-set' in c_low:
            return 'XR'
        return 'IOS'


def extract_hostname(config_text: str) -> str:
    """설정에서 hostname을 추출."""
    match = re.search(r'^\s*hostname\s+(\S+)', config_text, re.M | re.I)
    return match.group(1) if match else "Unknown"


def get_section_key(line: str) -> str:
    """명령어 라인의 첫 단어를 기반으로 섹션 키 추출."""
    line = line.strip()
    if not line or line.startswith('!'):
        return ''
    if line.startswith('logging synchronous'):
        return 'line'

    parts = line.split()
    if not parts:
        return ''

    first_word = parts[0].lower()
    if first_word in ('class-map', 'policy-map'):
        return first_word

    if parts[0] in TWO_WORD_PREFIXES and len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return parts[0]


def auto_split_sections(config_text: str) -> dict:
    """
    설정을 논리적 섹션으로 분할.
    들여쓰기 및 주요 키워드를 기준으로 그룹화.
    """
    sections = {}
    current_key = "GLOBAL"
    current_lines = []
    mergeable_sections = {
        'router', 'ip', 'vrf', 'spanning-tree', 'logging',
        'snmp-server', 'class-map', 'policy-map', 'username', 'snmp'
    }

    for line in config_text.splitlines():
        if not line.strip():
            continue
        if SKIP_RE.match(line):
            continue

        is_indented = line.startswith(' ') or line.startswith('\t')

        if not is_indented:
            new_key = get_section_key(line)
            is_same_group = False
            if new_key == current_key and current_key in mergeable_sections:
                is_same_group = True
            if current_key != "GLOBAL" and new_key != current_key:
                is_same_group = False

            if is_same_group:
                current_lines.append(line)
            else:
                if current_lines:
                    sections.setdefault(current_key, []).append("\n".join(current_lines))
                current_key = new_key if new_key else "GLOBAL"
                current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.setdefault(current_key, []).append("\n".join(current_lines))

    return sections


def node_to_dict(node) -> dict:
    return {
        "line": node.line,
        "depth": getattr(node, "depth", 0),
        "children": [node_to_dict(c) for c in getattr(node, "children", [])]
    }


def is_l2_interface(node, config_text: str = "") -> bool:
    """
    인터페이스 노드가 L2 스위치포트인지 L3 라우티드 포트인지 판별.
    """
    line = node.line.strip()
    parts = line.split()
    if len(parts) < 2:
        return False
    intf_name = parts[1]
    intf_lower = intf_name.lower()

    # 1. 논리 L3 인터페이스 타입
    if any(intf_lower.startswith(p) for p in ('loopback', 'tunnel', 'bdi', 'dialer', 'mgmt', 'null', 'nve')):
        return False
    if '.' in intf_name:  # 서브인터페이스 (예: Gi0/0.100)
        return False
    if intf_lower.startswith('vlan'):  # SVI 인터페이스
        return False

    children_lines = [c.line.strip().lower() for c in getattr(node, 'children', [])]

    # 2. 하위 설정에서 명시적 L3 판별
    for cline in children_lines:
        if cline.startswith('ip address') or cline.startswith('ipv6 address'):
            return False
        if cline.startswith('vrf forwarding') or cline.startswith('ip vrf forwarding'):
            return False
        if cline.startswith('no switchport'):
            return False
        if cline.startswith('encapsulation dot1q'):
            return False
        if cline.startswith('ip helper-address') or cline.startswith('ip router ospf'):
            return False

    # 3. 하위 설정에서 명시적 L2 판별
    for cline in children_lines:
        if cline.startswith('switchport'):
            return True
        if cline.startswith('spanning-tree'):
            return True
        if cline.startswith('storm-control'):
            return True

    # 4. 스위치 환경의 기본 물리 포트인 경우 L2 판별
    is_switch = bool(re.search(r'^\s*(switch\s+\d+|vlan\s+\d+)', config_text, re.M | re.I))
    if is_switch:
        return True

    return False


def classify_block(node, config_text: str = "") -> tuple[str, str]:
    line = node.line.strip()
    parts = line.split()
    first = parts[0].lower() if parts else ''
    two = ' '.join(parts[:2]).lower() if len(parts) >= 2 else first

    # 1. Interface Group (L2 vs L3 구분하여 그룹화)
    if first == 'interface':
        if is_l2_interface(node, config_text):
            return 'interfaces_l2', 'L2 Interfaces (L2 인터페이스 그룹)'
        else:
            return 'interfaces_l3', 'L3 Interfaces (L3 인터페이스 그룹)'

    # 2. VLANs
    if first == 'vlan' and len(parts) >= 2 and parts[1].isdigit():
        return 'vlans', 'VLAN Configurations'

    # 3. VRFs
    if first == 'vrf' or two.startswith('ip vrf'):
        return 'vrfs', 'VRF Definitions'

    # 4. Lines
    if first == 'line':
        return 'lines', 'Management Lines (Con/VTY)'

    # 5. Routing protocols
    if first == 'router':
        proto = parts[1].upper() if len(parts) >= 2 else 'Router'
        return f'routing_{proto.lower()}', f'{proto} Routing'

    # 6. ACLs
    if two.startswith('ip access-list') or two.startswith('ipv6 access-list') or first == 'access-list':
        return 'access_lists', 'Access Lists (ACL)'

    # 7. Prefix lists
    if two.startswith('ip prefix-list') or two.startswith('ipv6 prefix-list'):
        return 'prefix_lists', 'Prefix Lists'

    # 8. Route maps
    if first == 'route-map':
        return 'route_maps', 'Route Maps'

    # 9. Banner
    if first == 'banner':
        return 'banner', 'Banner Settings'

    # 10. Standalone global groups
    if first in ('hostname', 'version', 'boot', 'service'):
        return 'identity', 'System & Global'
    if two.startswith('ip domain') or two.startswith('ip name-server'):
        return 'dns', 'DNS & Domain'
    if first == 'ntp':
        return 'ntp', 'NTP Configuration'
    if first == 'logging':
        return 'logging', 'Logging'
    if first == 'username':
        return 'users', 'Local Users'
    if first.startswith('spanning-tree'):
        return 'spanning_tree', 'Spanning-Tree'
    if two.startswith('ip route') or two.startswith('ipv6 route'):
        return 'routing_static', 'Static Routes'
    if first.startswith('snmp-server'):
        return 'snmp', 'SNMP'
    if first.startswith('aaa'):
        return 'aaa', 'AAA & Security'

    clean_first = re.sub(r'[^a-zA-Z0-9_]', '_', first)
    return f'custom_{clean_first}', f'{two.title()}'


def extract_all_blocks(config_text: str, os_hint: str = 'auto') -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    """
    cisco-config-parser의 ConfigTree를 사용하여 설정을 의미 있는 블록 트리로 분할.
    인터페이스는 요청에 따라 'L2 Interfaces (L2 인터페이스 그룹)'과
    'L3 Interfaces (L3 인터페이스 그룹)'으로 분리되어 그룹화됨.
    """
    platform = detect_platform(config_text, os_hint)
    parser = ConfigParser(config_text, platform=platform)
    try:
        model = parser.parse(include_raw_tree=True)
    except Exception:
        model = {}

    tree = ConfigTree(config_text)
    raw_sections = auto_split_sections(config_text)

    blocks_map: Dict[str, Dict[str, Any]] = {}
    block_order: List[str] = []

    for node in tree.root.children:
        block_id, block_title = classify_block(node, config_text)
        if block_id not in blocks_map:
            blocks_map[block_id] = {
                'block_id': block_id,
                'name': block_title,
                'nodes': []
            }
            block_order.append(block_id)
        blocks_map[block_id]['nodes'].append(node)

    blocks: List[Dict[str, Any]] = []
    for idx, bid in enumerate(block_order, 1):
        blk = blocks_map[bid]
        tree_nodes = [node_to_dict(n) for n in blk['nodes']]
        items = []
        raw_lines = []

        for n in blk['nodes']:
            raw_lines.append(n.line)
            if bid in ('interfaces_l2', 'interfaces_l3', 'interfaces'):
                # 인터페이스 그룹: 각 인터페이스가 상위 노드, 하위 명령어가 자식 노드
                intf_name = ' '.join(n.line.split()[1:]) if len(n.line.split()) > 1 else n.line
                clean_intf = re.sub(r'[^a-zA-Z0-9_]', '_', intf_name)
                group_prefix = 'L2 Interface' if bid == 'interfaces_l2' else 'L3 Interface'

                if not n.children:
                    items.append({
                        "id": f"{bid}.{clean_intf}.config",
                        "block_id": bid,
                        "section": bid,
                        "parent_node": n.line.strip(),
                        "command_line": n.line.strip(),
                        "label": f"{group_prefix} > {intf_name}",
                        "value": "configured",
                        "source": "cisco_config_parser",
                        "raw_block": n.line
                    })
                else:
                    for c in n.children:
                        raw_lines.append(" " + c.line)
                        c_line = c.line.strip()
                        c_parts = c_line.split()
                        c_val = " ".join(c_parts[1:]) if len(c_parts) > 1 else "enabled"
                        clean_child = re.sub(r'[^a-zA-Z0-9_]', '_', c_line)
                        items.append({
                            "id": f"{bid}.{clean_intf}.{clean_child}",
                            "block_id": bid,
                            "section": bid,
                            "parent_node": n.line.strip(),
                            "command_line": c_line,
                            "label": f"{intf_name} > {c_line}",
                            "value": c_val,
                            "source": "cisco_config_parser",
                            "raw_block": n.line + "\n " + c_line
                        })
            elif n.children:
                header = n.line.strip()
                clean_hdr = re.sub(r'[^a-zA-Z0-9_]', '_', header)
                for c in n.children:
                    raw_lines.append(" " + c.line)
                    c_line = c.line.strip()
                    c_parts = c_line.split()
                    c_val = " ".join(c_parts[1:]) if len(c_parts) > 1 else "enabled"
                    clean_child = re.sub(r'[^a-zA-Z0-9_]', '_', c_line)
                    items.append({
                        "id": f"{bid}.{clean_hdr}.{clean_child}",
                        "block_id": bid,
                        "section": bid,
                        "parent_node": header,
                        "command_line": c_line,
                        "label": f"{header} > {c_line}",
                        "value": c_val,
                        "source": "cisco_config_parser",
                        "raw_block": header + "\n " + c_line
                    })
            else:
                parts = n.line.strip().split()
                val = " ".join(parts[1:]) if len(parts) > 1 else "enabled"
                clean_line = re.sub(r'[^a-zA-Z0-9_]', '_', n.line.strip())
                items.append({
                    "id": f"{bid}.{clean_line}",
                    "block_id": bid,
                    "section": bid,
                    "parent_node": "",
                    "command_line": n.line.strip(),
                    "label": n.line.strip(),
                    "value": val,
                    "source": "cisco_config_parser",
                    "raw_block": n.line.strip()
                })

        blocks.append({
            "block_id": bid,
            "name": blk['name'],
            "icon": "",
            "order": idx,
            "enabled": True,
            "item_count": len(items),
            "items": items,
            "tree_nodes": tree_nodes,
            "raw_text": "\n".join(raw_lines)
        })

    return blocks, model, raw_sections


def sanitize_config(raw_text: str) -> Tuple[str, Dict[str, Any]]:
    """
    설정 파일에서 순수 Cisco running-config 본문만 지능적으로 추출하고,
    설정과 무관한 노이즈(프롬프트, Show 명령어 출력, 라우팅 테이블, 인터페이스 카운터 등)를 감지 및 분리.
    """
    if not raw_text:
        return "", {"has_noise": False, "pre_noise_count": 0, "post_noise_count": 0}

    # 1. BOM 제거
    if raw_text.startswith('\ufeff'):
        raw_text = raw_text[1:]

    lines = raw_text.splitlines()
    total_lines = len(lines)

    # 2. 시작 지점 감지
    start_idx = 0
    pre_noise = []
    found_start = False

    for idx, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        # 헤더 안내 문구
        if re.match(r'^(Building configuration|Current configuration|Last configuration change)', s, re.I):
            continue
        if s.startswith('!') and not found_start:
            continue
        # Cisco 설정의 첫 시작 키워드
        if re.match(r'^(version\s+\d|hostname\s+\S|service\s+|boot\s+|interface\s+|vrf\s+|ip\s+|spanning-tree|ntp|logging|crypto|aaa|username|line|vlan|router\s+)', s, re.I):
            start_idx = idx
            found_start = True
            break
        pre_noise.append(s)

    # 3. 종료 지점 ('end') 감지
    end_idx = total_lines
    has_end = False
    post_noise = []

    for idx in range(start_idx, total_lines):
        s = lines[idx].strip()
        if s == 'end':
            end_idx = idx + 1
            has_end = True
            post_noise = lines[end_idx:]
            break

    pure_lines = lines[start_idx:end_idx]
    pure_config = "\n".join(pure_lines)

    noise_info = {
        "has_noise": len(pre_noise) > 0 or len(post_noise) > 0,
        "pre_noise_count": len(pre_noise),
        "post_noise_count": len(post_noise),
        "pre_noise_sample": pre_noise[:3],
        "post_noise_sample": [l.strip() for l in post_noise if l.strip()][:3],
        "total_lines": total_lines,
        "config_lines": len(pure_lines),
    }
    return pure_config, noise_info


def parse_config(config_text: str, os_type: str = 'auto') -> dict:
    """
    설정 텍스트를 파싱하여 blocks 및 sections 구조를 생성.
    파일에 포함된 비설정 노이즈(Show 커맨드, 세션 로그 등)를 자동 정제.
    """
    pure_config, noise_info = sanitize_config(config_text)

    if os_type == 'auto':
        os_type = detect_os(pure_config)

    blocks, model, raw_sections = extract_all_blocks(pure_config, os_type)
    hostname = model.get("hostname") or extract_hostname(pure_config)

    # sections 사전 구축 (comparator.py 호환)
    sections = {}
    for sec_key, raw_b in raw_sections.items():
        entry = {"raw": raw_b}
        # cisco-config-parser 모델 매핑
        s_low = sec_key.lower()
        if s_low.startswith('interface'):
            entry["parsed"] = {
                "l3": model.get("l3_interfaces", []),
                "l2_access": model.get("l2_access_interfaces", []),
                "l2_trunk": model.get("l2_trunk_interfaces", [])
            }
            entry["genie"] = entry["parsed"]  # 하위 호환
        elif s_low.startswith('line'):
            entry["parsed"] = (model.get("identity") or {}).get("lines", [])
            entry["genie"] = entry["parsed"]
        elif s_low.startswith('vrf'):
            entry["parsed"] = model.get("vrfs", [])
            entry["genie"] = entry["parsed"]
        elif s_low.startswith('banner'):
            entry["parsed"] = model.get("banner", "")
            entry["genie"] = entry["parsed"]
        elif s_low.startswith('router'):
            entry["parsed"] = model.get("routing", {})
            entry["genie"] = entry["parsed"]
        else:
            entry["parsed"] = None

        sections[sec_key] = entry

    return {
        "hostname": hostname,
        "os": os_type,
        "platform": model.get("platform", "IOS"),
        "blocks": blocks,
        "sections": sections,
        "structured": model,
        "global_genie": model,  # 하위 호환
        "config_tree": model.get("config_tree", []),
        "noise_info": noise_info,
        "pure_config": pure_config
    }


def flatten_for_ui(parsed: dict) -> list:
    """
    UI 및 템플릿 구성을 위해 아이템 리스트로 평탄화.
    blocks가 정의되어 있으면 블록 순서 및 활성화 여부에 따라 정렬하여 반환.
    """
    blocks = parsed.get("blocks")
    if blocks:
        items = []
        for block in blocks:
            if not block.get("enabled", True):
                continue
            for item in block.get("items", []):
                items.append(item)
        return items

    # fallback (레거시 데이터용)
    items = []
    for section_key, entry in parsed.get("sections", {}).items():
        raw_blocks = entry.get("raw", [])
        for i, block in enumerate(raw_blocks):
            lines = [l for l in block.splitlines() if l.strip()]
            if not lines:
                continue
            header = lines[0].strip()
            children = [l.strip() for l in lines[1:]]
            if children:
                for child in children:
                    c_parts = child.split()
                    label_part = f"{header} > {c_parts[0]}" if len(c_parts) > 1 else f"{header} > {child}"
                    value_part = " ".join(c_parts[1:]) if len(c_parts) > 1 else "enabled"
                    items.append({
                        "id": f"{section_key}.{i}.{child}",
                        "section": section_key,
                        "label": label_part,
                        "value": value_part,
                        "source": "raw",
                        "raw_block": block
                    })
            else:
                items.append({
                    "id": f"{section_key}.raw.{i}",
                    "section": section_key,
                    "label": header,
                    "value": "enabled",
                    "source": "raw",
                    "raw_block": block
                })
    return items
