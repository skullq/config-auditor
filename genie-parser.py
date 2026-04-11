"""
genie-parser.py

[전략]
1. 설정 파일을 미리 가정하지 않고, IOS 설정 형식의 규칙만으로 섹션을 동적 분리
   - 들여쓰기 없이 시작하는 줄 → 새 섹션의 시작
   - 들여쓰기 있는 줄       → 직전 섹션의 하위 명령
2. 발견된 섹션마다 Genie 파서가 있으면 구조화, 없으면 raw 텍스트로 보관
"""

import re
import pprint
from collections import defaultdict
from genie.metaparser.util.exceptions import SchemaEmptyParserError

# ─────────────────────────────────────────────────────────────────
# 1. 설정 파일 읽기
# ─────────────────────────────────────────────────────────────────
with open("r1.cfg", "r") as f:
    raw_config = f.read()


# ─────────────────────────────────────────────────────────────────
# 2. IOS 설정 형식 규칙으로 섹션 자동 분리 (hardcode 없음)
#    규칙:
#      - '!' → 섹션 구분자 (무시)
#      - 들여쓰기 없이 시작 → 새 섹션의 시작
#      - 들여쓰기 있는 줄   → 현재 섹션의 서브 명령
#      - 건너뛸 라인: 빈 줄, 장비 프롬프트, "Building/Current configuration" 등
# ─────────────────────────────────────────────────────────────────

SKIP_RE = re.compile(
    r'^\s*$'                           # 빈 줄
    r'|^!'                             # IOS 구분자
    r'|^Building configuration'        # show run 헤더
    r'|^Current configuration'         # show run 헤더
    r'|^end\s*$'                       # 마지막 end
    r'|^\S+[#>]\s*sh'                  # 장비 프롬프트 (e.g. R1#sh run)
    r'|\s*quit\s*$'                    # PKI 인증서 quit
)

def get_section_key(line: str) -> str:
    """한 라인에서 섹션 식별 키를 추출한다 (첫 1~2 단어)."""
    parts = line.split()
    if len(parts) == 0:
        return 'unknown'
    # 'router ospf', 'ip route', 'crypto pki' 등 2단어가 의미있는 경우
    TWO_WORD_PREFIXES = {
        'router', 'ip', 'ipv6', 'crypto', 'no', 'vrf',
        'spanning-tree', 'line', 'snmp-server', 'ntp',
        'logging', 'aaa', 'username', 'boot',
    }
    if parts[0] in TWO_WORD_PREFIXES and len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return parts[0]


def auto_split_sections(config: str) -> dict[str, list[str]]:
    """
    설정 텍스트를 섹션별 raw 블록의 리스트로 자동 분리한다.
    반환: { 'section_key': ['블록1 텍스트', '블록2 텍스트', ...] }
    """
    sections: dict[str, list[str]] = defaultdict(list)
    current_lines: list[str] = []
    current_key: str | None = None

    def flush():
        nonlocal current_lines, current_key
        if current_key and current_lines:
            block_text = '\n'.join(current_lines).rstrip()
            if block_text:
                sections[current_key].append(block_text)
        current_lines = []
        current_key = None

    for line in config.splitlines():
        # 건너뛸 라인
        if SKIP_RE.match(line):
            continue

        # 들여쓰기 없이 시작하는 줄 → 새 섹션
        if not line.startswith(' ') and not line.startswith('\t'):
            flush()
            current_key = get_section_key(line)
            current_lines = [line]
        else:
            # 서브 명령: 현재 섹션에 추가
            if current_key is not None:
                current_lines.append(line)
            # else: 섹션 헤더 없이 들여쓰진 줄은 무시

    flush()
    return dict(sections)


sections = auto_split_sections(raw_config)

print("=" * 60)
print("▶ 자동 탐지된 섹션 목록")
print("=" * 60)
for key, blocks in sorted(sections.items()):
    print(f"  ✔  [{key}]  — {len(blocks)}개 블록")


# ─────────────────────────────────────────────────────────────────
# 3. Genie 파서 매핑 테이블
#    (Genie에 파서가 존재하는 섹션만 정의 — 새 파일에도 범용 적용됨)
#    탐지된 섹션과 교집합에 해당하는 것만 실행됨
# ─────────────────────────────────────────────────────────────────
from genie.libs.parser.iosxe.show_run import (
    ShowRunInterface,
    ShowRunSectionBgp,
    ShowRunningConfigVrf,
    ShowRunRoute,
    ShowRunningConfigNve,
    ShowRunPolicyMap,
)

GENIE_PARSER_MAP = {
    # 탐지 섹션 키   :  (레이블,  파서 클래스)
    'interface'      : ('인터페이스',    ShowRunInterface),
    'router bgp'     : ('BGP',           ShowRunSectionBgp),
    'vrf definition' : ('VRF',           ShowRunningConfigVrf),
    'ip route'       : ('정적 경로',     ShowRunRoute),
    'nve'            : ('NVE',           ShowRunningConfigNve),
}


# ─────────────────────────────────────────────────────────────────
# 4. 탐지된 섹션에 Genie 파서 적용 (없으면 raw 보존)
# ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("▶ 파싱 처리")
print("=" * 60)

result: dict = {}

for section_key, blocks in sections.items():
    combined_text = '\n'.join(blocks)  # 여러 블록을 이어붙여 파서에 전달

    if section_key in GENIE_PARSER_MAP:
        label, ParserClass = GENIE_PARSER_MAP[section_key]
        try:
            parsed = ParserClass(device=None).parse(output=combined_text)
            result[section_key] = parsed
            print(f"  ✔  [{section_key}]  → Genie 구조화 파싱 성공 ({label})")
            continue
        except SchemaEmptyParserError:
            pass
        except Exception as e:
            print(f"  ⚠  [{section_key}]  → Genie 파싱 실패 ({e}), raw로 보존")

    # Genie 파서 없음 or 실패 → raw 텍스트 블록으로 보존
    result[section_key] = blocks
    status = "raw 보존" if section_key not in GENIE_PARSER_MAP else "raw 대체"
    print(f"  ○  [{section_key}]  → {status}  ({len(blocks)}개 블록)")


# ─────────────────────────────────────────────────────────────────
# 5. 전체 결과 출력
# ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("▶ 최종 파싱 결과")
print("=" * 60)
pprint.pprint(result)
