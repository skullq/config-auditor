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

# 2단어로 식별해야 의미가 생기는 첫 단어 목록
TWO_WORD_PREFIXES = {
    'router', 'ip', 'ipv6', 'crypto', 'no', 'vrf',
    'spanning-tree', 'line', 'snmp-server', 'ntp',
    'logging', 'aaa', 'username', 'boot',
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

    for line in config.splitlines():
        if SKIP_RE.match(line):
            continue
        if not line.startswith((' ', '\t')):
            flush()
            current_key = get_section_key(line)
            current_lines = [line]
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
        'interface': 'ShowRunInterface',
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
                first_line = block.splitlines()[0] if block else section_key
                items.append({
                    "id": f"{section_key}.raw.{i}",
                    "section": section_key,
                    "label": first_line,
                    "value": block,
                    "source": "raw",
                    "raw_block": block,
                })

    return items
