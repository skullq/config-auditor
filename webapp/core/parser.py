import re
import os
import json
from unittest.mock import MagicMock

# Genie 및 pyATS 관련 임포트는 함수 내부에서 동적으로 진행하여 의존성 최소화

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
    if 'show running-config' in config_text.lower():
        if 'ios-xe' in config_text.lower() or 'ios-xr' in config_text.lower():
            return 'iosxe'
    if 'nx-os' in config_text.lower():
        return 'nxos'
    if 'ios-xr' in config_text.lower():
        return 'iosxr'
    if 'aireos' in config_text.lower():
        return 'aireos'
    return 'iosxe' # 기본값

def extract_hostname(config_text: str) -> str:
    """설정에서 hostname을 추출."""
    match = re.search(r'^hostname\s+(\S+)', config_text, re.M)
    return match.group(1) if match else "Unknown"

def get_section_key(line: str) -> str:
    """명령어 라인의 첫 단어를 기반으로 섹션 키 추출. 특수 예외 처리 포함."""
    line = line.strip()
    if not line or line.startswith('!'): return ''
    
    # 특수 예외: 'logging synchronous'는 무조건 line 섹션으로 귀속
    if line.startswith('logging synchronous'):
        return 'line'

    parts = line.split()
    if not parts: return ''
    
    # class-map, policy-map은 첫 단어만 섹션 키로 사용하여 그룹화
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
    
    # 병합이 필요한 주요 섹션들
    mergeable_sections = {'router', 'ip', 'vrf', 'spanning-tree', 'logging', 'snmp-server', 'class-map', 'policy-map', 'username', 'snmp'}

    for line in config_text.splitlines():
        if not line.strip(): continue
        if SKIP_RE.match(line): continue
        
        # 들여쓰기 확인
        is_indented = line.startswith(' ') or line.startswith('\t')
        
        if not is_indented:
            new_key = get_section_key(line)
            
            # 머지 가능 여부 판단: 정확히 동일한 키이거나 명시적 머지 대상인 경우만 합침
            is_same_group = False
            if new_key == current_key and current_key in mergeable_sections:
                is_same_group = True
            
            # 특수 예외: 'ip route'나 'ip forward-protocol' 등은 같은 키라도 각각 분리하는게 나을 수 있음
            # 여기서는 전역 명령어(GLOBAL)들이 서로 엉키지 않게 하는 것이 핵심
            if current_key != "GLOBAL" and new_key != current_key:
                is_same_group = False

            if is_same_group:
                current_lines.append(line)
            else:
                # 새로운 섹션 시작
                if current_lines:
                    sections.setdefault(current_key, []).append("\n".join(current_lines))
                current_key = new_key if new_key else "GLOBAL"
                current_lines = [line]
        else:
            current_lines.append(line)
            
    if current_lines:
        sections.setdefault(current_key, []).append("\n".join(current_lines))
        
    return sections

def _get_parser_module_path(os_type: str) -> str:
    mapping = {
        'iosxe': 'genie.libs.parser.iosxe.show_run',
        'nxos':  'genie.libs.parser.nxos.show_run',
        'iosxr': 'genie.libs.parser.iosxr.show_run',
        'ios':   'genie.libs.parser.ios.show_run',
        'aireos':'genie.libs.parser.aireos.show_run', 
    }
    return mapping.get(os_type.lower(), 'genie.libs.parser.iosxe.show_run')

def _load_parsers_for_os(os_type: str) -> dict:
    """지정된 OS에 필요한 Genie 파서들을 로드."""
    parsers = {}
    import importlib
    
    mod_path = _get_parser_module_path(os_type)
    targets = {
        'all': ['ShowRunningConfig', 'ShowRun'],
        'line': ['ShowRunningConfigLine', 'ShowRunLine'],
        'interface': ['ShowRunInterface', 'ShowRunningConfigInterface'],
        'vrf': ['ShowRunningConfigVrf', 'ShowRunSectionVrfDefinition'],
        'route': ['ShowRunRoute'],
        'bgp': ['ShowRunSectionBgp']
    }

    try:
        mod = importlib.import_module(mod_path)
        for key, candidates in targets.items():
            for cname in candidates:
                if hasattr(mod, cname):
                    parsers[key] = getattr(mod, cname)
                    break
        
        # 만약 ShowRunningConfig를 못 찾았다면 alternate 모듈 탐색
        if 'all' not in parsers:
            try:
                alt_mod_path = mod_path.replace('show_run', 'show_running_config')
                alt_mod = importlib.import_module(alt_mod_path)
                for cname in targets['all']:
                    if hasattr(alt_mod, cname):
                        parsers['all'] = getattr(alt_mod, cname)
                        break
            except Exception: pass
    except Exception:
        pass

    return parsers

def parse_config(config_text: str, os_type: str = 'auto') -> dict:
    if os_type == 'auto': os_type = detect_os(config_text)
    hostname = extract_hostname(config_text)
    os_parsers = _load_parsers_for_os(os_type)
    
    # 1. 입력 데이터 정제 (Genie 파서는 매우 민감함)
    lines = []
    for line in config_text.splitlines():
        if SKIP_RE.match(line): continue
        if any(x in line for x in ('Building configuration', 'Current configuration', '!!')):
            continue
        lines.append(line)
    cleaned_cfg = "\n".join(lines).strip()

    # 2. Genie 분석
    global_genie = None
    if 'all' in os_parsers:
        try:
            parser_inst = os_parsers['all'](device=None)
            global_genie = parser_inst.parse(output=cleaned_cfg)
        except Exception: pass

    # 개별 섹션 분석 (fallback)
    raw_sections = auto_split_sections(config_text)
    result = {}
    for section_key, blocks in raw_sections.items():
        entry = {"raw": blocks}
        combined = '\n'.join(blocks)
        
        parser_key = None
        s_lower = section_key.lower()
        if s_lower.startswith('interface'): parser_key = 'interface'
        elif s_lower.startswith('line'): parser_key = 'line'
        elif s_lower.startswith('vrf'): parser_key = 'vrf'
        
        if parser_key and parser_key in os_parsers:
            try:
                parser_inst = os_parsers[parser_key](device=None)
                p = parser_inst.parse(output=combined)
                if p: entry["genie"] = p
            except Exception: pass
            
        result[section_key] = entry

    return {
        "hostname": hostname,
        "os": os_type,
        "sections": result,
        "global_genie": global_genie
    }

def flatten_for_ui(parsed: dict) -> list:
    items = []
    processed_genie_roots = set()

    def _flatten(obj, path, section, raw_block=None):
        if isinstance(obj, dict):
            for k, v in obj.items():
                # 딕셔너리 하위에 실질적 데이터가 있으면 계속 탐색
                _flatten(v, path + [str(k)], section, raw_block)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _flatten(v, path + [str(i)], section, raw_block)
        else:
            # 최종 값 도달
            val_str = str(obj)
            # 만약 값이 True/False 인데 경로의 마지막이 의미있는 단어라면 경로를 다듬음
            display_label = " > ".join(path)
            
            # 불필요한 Boolean 값 정제 (값이 True이면 라벨 자체가 의미를 가짐)
            if val_str == "True":
                val_str = "enabled"
            elif val_str == "False":
                val_str = "disabled"

            items.append({
                "id": '.'.join(path),
                "section": section,
                "label": display_label,
                "value": val_str,
                "source": "genie",
                "raw_block": raw_block,
            })

    # 1. Global Genie 데이터 우선 처리
    global_genie = parsed.get("global_genie")
    if global_genie:
        for root_key, content in global_genie.items():
            _flatten(content, [root_key], root_key)
            processed_genie_roots.add(root_key.lower().replace('_', '-'))

    # 2. 개별 섹션 데이터 처리
    for section_key, entry in parsed.get("sections", {}).items():
        s_base = section_key.lower().split()[0]
        if s_base in processed_genie_roots: continue
        
        raw_blocks = entry.get("raw", [])
        if "genie" in entry:
            _flatten(entry["genie"], [section_key], section_key, "\n".join(raw_blocks))
        else:
            for i, block in enumerate(raw_blocks):
                lines = [l for l in block.splitlines() if l.strip()]
                if not lines: continue
                header = lines[0].strip()
                children = [l.strip() for l in lines[1:]]
                
                if children:
                    for child in children:
                        # 지능형 값 분리 (마지막 단어를 필드로 분리 시도)
                        c_parts = child.split()
                        if len(c_parts) > 1:
                            # 'description EWLC Control' -> label: '... > description', value: 'EWLC Control'
                            label_part = f"{header} > {c_parts[0]}"
                            value_part = " ".join(c_parts[1:])
                        else:
                            label_part = f"{header} > {child}"
                            value_part = "enabled"

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
