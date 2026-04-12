"""
core/parser.py
Cisco IOS/IOS-XE 설정 파일을 자동으로 섹션 분리하고 Genie 파서로 구조화.
"""

import re
from collections import defaultdict
from genie.metaparser.util.exceptions import SchemaEmptyParserError

# ── IOS cfg 포맷에서 제거할 줄 패턴 ───────────────────────────────────
SKIP_RE = re.compile(
    r'^\s*$'
    r'|^!'
    r'|^Building configuration'
    r'|^Current configuration'
    r'|^end\s*$'
    r'|^\S+[#>]\s*sh'
    r'|\s*quit\s*$'
)

TWO_WORD_PREFIXES = {
    'router', 'ip', 'ipv4', 'ipv6', 'crypto', 'no', 'vrf',
    'spanning-tree', 'line', 'snmp-server', 'ntp',
    'logging', 'username', 'boot',
}


def get_section_key(line: str) -> str:
    parts = line.split()
    if not parts:
        return 'unknown'
    if parts[0] in TWO_WORD_PREFIXES and len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return parts[0]


def auto_split_sections(config: str) -> dict:
    """
    설정 텍스트를 섹션 키 → raw 블록 리스트로 자동 분리.
    사전 지식 없이 IOS 형식 규칙(들여쓰기)만 사용.
    """
    sections = defaultdict(list)
    current_lines = []
    current_key = None

    def flush():
        nonlocal current_lines, current_key
        if current_key and current_lines:
            block = '\n'.join(current_lines).rstrip()
            if block:
                sections[current_key].append(block)
        current_lines = []
        current_key = None

    banner_mode = False
    banner_delimiter = ''
    mergeable_sections = {'feature', 'ip route', 'ipv4 route', 'ipv6 route', 'service', 'ntp', 'spanning-tree', 'snmp-server'}
    acl_mode = False

    for line in config.splitlines():
        stripped = line.strip()
        is_indented = line.startswith((' ', '\t'))

        # ── Banner Mode 하위 라인 처리 (SKIP_RE보다 우선) ──
        if banner_mode:
            current_lines.append(line)
            # 종료 조건: 구분자가 포함되어 있거나 (보통 줄 끝에 옴), 
            # 안전장치: 구분자를 못 찾았더라도 새로운 주요 섹션이 시작되면 종료
            is_new_section = not is_indented and any(stripped.startswith(p) for p in ['interface ', 'router ', 'line ', 'ip route', 'snmp-server', 'username '])
            if (banner_delimiter and banner_delimiter in line) or is_new_section:
                if is_new_section:
                    # 새로운 섹션 줄은 현재 배너에서 제외하고 다음 루프에서 처리하도록 함
                    current_lines.pop()
                    banner_mode = False
                    flush()
                    # 이 줄을 다시 처리하기 위해 continue가 아닌 로직 흐름 유지 필요
                    # 여기서는 그냥 루프를 다시 돌릴 수 없으므로, 일단 flush하고 current_lines를 이 줄로 세팅
                    current_key = get_section_key(line)
                    current_lines = [line]
                    if current_key in ('ip access-list', 'access-list'): acl_mode = True
                else:
                    banner_mode = False
                    flush()
            continue

        if SKIP_RE.match(line):
            if stripped == '!':
                acl_mode = False
            continue
            
        # ── Banner 시작 감지 ──
        if stripped.startswith('banner '):
            flush()
            # Cisco banner [motd|login] <delim> <text> <delim>
            parts = stripped.split()
            if len(parts) >= 2:
                # 'motd' 또는 'login' 다음 위치 찾기
                idx = line.find(parts[1])
                if idx != -1:
                    remaining = line[idx + len(parts[1]):].lstrip()
                    if remaining:
                        delim = remaining[0]
                        banner_delimiter = delim
                        banner_mode = True
                        current_key = 'banner'
                        current_lines = [line]
                        
                        # 시작 줄에 종료 구분자가 하나 더 있으면 한 줄짜리 배너
                        if remaining[1:].find(delim) != -1:
                            banner_mode = False
                            flush()
                        continue

        is_acl_seq = False
        if acl_mode and not is_indented:
            # Check if line looks like an ACL sequence inside an ACL context
            if re.match(r'^(\d+\s+)?(permit|deny|remark)\s+', stripped, re.I):
                is_acl_seq = True

        if not is_indented and not is_acl_seq:
            new_key = get_section_key(line)
            
            # 머지 가능한 섹션이고 이전과 동일한 키라면 flush 하지 않고 합침
            if current_key in mergeable_sections and new_key == current_key:
                current_lines.append(line)
            else:
                flush()
                current_key = new_key
                current_lines = [line]
            
            # ACL block detection
            if current_key in ('ip access-list', 'ipv4 access-list', 'ipv6 access-list', 'mac access-list', 'access-list'):
                acl_mode = True
            else:
                acl_mode = False
        else:
            if current_key is not None:
                current_lines.append(line)

    flush()
    return dict(sections)


def detect_os(config_text: str) -> str:
    """설정 텍스트의 특징을 분석하여 OS 타입을 자동 감지."""
    lines = config_text[:10000].splitlines() # 상단 상당 부분을 분석
    text_sample = '\n'.join(lines)

    # 1. IOS-XR: 특정 프롬프트 또는 전용 명령어 패턴
    if re.search(r'RP/0/RP\d+/CPU\d+|RP/0/RSP\d+/CPU\d+', text_sample):
        return 'iosxr'
    if 'Building configuration' in text_sample and '!!' in text_sample:
        # IOS-XR은 보통 섹션 구분을 !! 로 함
        return 'iosxr'

    # 2. NX-OS: 특징적인 feature 명령어 등
    if 'feature ' in text_sample or 'system qos' in text_sample:
        return 'nxos'
    if 'NX-OS' in text_sample:
        return 'nxos'

    # 3. AireOS (WLC): (Cisco Controller) 프롬프트 또는 전용 설정
    if '(Cisco Controller)' in text_sample or 'config wlan' in text_sample:
        return 'aireos'

    # 4. IOS-XE vs Classic IOS
    # IOS-XE는 보통 버전이 16.x, 17.x 이상이거나 license udi 등이 있음
    version_match = re.search(r'version\s+(\d+\.\d+)', text_sample)
    if version_match:
        try:
            v_str = version_match.group(1)
            v = float(v_str)
            if v >= 16.0 or 'license udi' in text_sample:
                return 'iosxe'
            return 'ios'
        except ValueError:
            pass

    # 5. 기타 패턴 매칭 (기본값 전략)
    if 'interface ' in text_sample and 'ip address' in text_sample:
        # 일반적인 IOS/XE 패턴
        return 'iosxe'

    return 'iosxe'


def extract_hostname(config: str) -> str | None:
    """설정에서 hostname을 추출."""
    for line in config.splitlines()[:200]: # 상단 200줄 이내에서 탐색
        m = re.match(r'^hostname\s+(\S+)', line.strip())
        if m:
            return m.group(1)
    return None


# ── Genie 파서 매핑 (멀티 OS 지원) ─────────────────────────────────────────

def _get_parser_module_path(os_type: str) -> str:
    """OS 타입에 따른 Genie 파서 모듈 경로 반환."""
    mapping = {
        'iosxe': 'genie.libs.parser.iosxe.show_run',
        'nxos':  'genie.libs.parser.nxos.show_run',
        'iosxr': 'genie.libs.parser.iosxr.show_run',
        'ios':   'genie.libs.parser.ios.show_run',
        'aireos':'genie.libs.parser.aireos.show_run', 
    }
    return mapping.get(os_type.lower(), 'genie.libs.parser.iosxe.show_run')


def _load_parsers_for_os(os_type: str) -> dict:
    """지정된 OS에 필요한 Genie 파서들을 동적 로드."""
    parsers = {}
    import importlib
    
    # OS별 파서 클래스 이름 매핑 (일반적으로 ShowRunInterface 등은 기능적으로 유사)
    parser_classes = {
        # 'interface': 'ShowRunInterface',  # 인터페이스 파편화 방지를 위해 RAW 분석으로 우회
        'vrf definition': 'ShowRunningConfigVrf',
        'ip route': 'ShowRunRoute',
        'nve': 'ShowRunningConfigNve',
        'router bgp': 'ShowRunSectionBgp',
    }

    try:
        mod_path = _get_parser_module_path(os_type)
        mod = importlib.import_module(mod_path)
        for key, class_name in parser_classes.items():
            if hasattr(mod, class_name):
                parsers[key] = getattr(mod, class_name)
    except Exception:
        pass
    
    return parsers


def parse_config(config_text: str, os_type: str = 'auto') -> dict:
    """
    설정 파일 텍스트를 멀티 OS 기반으로 분석.
    os_type='auto'인 경우 자동 감지 수행.
    """
    if os_type == 'auto':
        os_type = detect_os(config_text)
    
    hostname = extract_hostname(config_text)
    raw_sections = auto_split_sections(config_text)
    
    # 해당 OS용 파서 로드
    os_parsers = _load_parsers_for_os(os_type)
    result = {}

    for section_key, blocks in raw_sections.items():
        combined = '\n'.join(blocks)
        entry = {"raw": blocks}

        if section_key in os_parsers:
            ParserClass = os_parsers[section_key]
            try:
                parser_inst = ParserClass(device=None)
                parsed = parser_inst.parse(output=combined)
                if parsed:
                    entry["genie"] = parsed
            except SchemaEmptyParserError:
                pass
            except Exception:
                pass

        result[section_key] = entry

    return {
        "hostname": hostname,
        "os": os_type,
        "sections": result,
    }


def flatten_for_ui(parsed: dict) -> list[dict]:
    """
    parse_config() 결과에서 UI 체크박스용 flat 항목 목록을 생성.

    각 항목:
    {
      "id": "interface.GigabitEthernet0/0/0.ipv4.ip",
      "section": "interface",
      "label": "interface > GigabitEthernet0/0/0 > ipv4 > ip",
      "value": "172.16.254.34",
      "source": "genie" | "raw",
      "raw_block": "...",
    }
    """
    items = []

    def _flatten(obj, path: list, section: str, raw_block: str):
        if isinstance(obj, dict):
            for k, v in obj.items():
                _flatten(v, path + [str(k)], section, raw_block)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _flatten(v, path + [str(i)], section, raw_block)
        else:
            item_id = '.'.join(path)
            items.append({
                "id": item_id,
                "section": section,
                "label": " > ".join(path),
                "value": str(obj) if obj is not None else "",
                "source": "genie",
                "raw_block": raw_block,
            })

    for section_key, entry in parsed.get("sections", {}).items():
        raw_blocks = entry.get("raw", [])
        raw_text = '\n'.join(raw_blocks)

        if "genie" in entry:
            _flatten(entry["genie"], [section_key], section_key, raw_text)
        else:
            # raw 섹션: 각 블록을 하나의 항목으로
            for i, block in enumerate(raw_blocks):
                lines = block.splitlines()
                first_line = lines[0] if lines else section_key
                
                # RAW 블록 중 세부 설정(들여쓰기)이 있는 구조 분할 (인터페이스, ACL 등 파편화 방지)
                # 단, 'feature', 'ip route' 같은 단순 나열형 섹션은 개별 줄을 각각 항목으로 취급
                if len(lines) > 1 and section_key not in ('banner', 'certificate'):
                    if section_key in ('feature', 'ip route', 'ipv4 route', 'ipv6 route', 'service', 'ntp', 'spanning-tree', 'snmp-server'):
                        for j, line in enumerate(lines):
                            items.append({
                                "id": f"{section_key}.raw.{i}.{j}",
                                "section": section_key,
                                "label": line.strip(),
                                "value": line.strip(),
                                "source": "raw",
                                "raw_block": line.strip(),
                                "parent_header": section_key # 'feature' 자체를 헤더로 사용
                            })
                    else:
                        header = first_line
                        for j, line in enumerate(lines[1:], start=1):
                            if not line.strip(): continue
                            items.append({
                                "id": f"{section_key}.raw.{i}.{j}",
                                "section": section_key,
                                "label": line.strip(),
                                "value": line.strip(),
                                "source": "raw",
                                "raw_block": line.strip(),
                                "parent_header": header
                            })
                else:
                    items.append({
                        "id": f"{section_key}.raw.{i}",
                        "section": section_key,
                        "label": first_line,
                        "value": block,
                        "source": "raw",
                        "raw_block": block,
                        "parent_header": first_line
                    })

    return items
