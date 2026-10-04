---
description: Network Config Auditor 필수 테스트 및 무결성 검증 규칙
globs: ["**/*"]
---

# Network Config Auditor — AI 검증 규칙 및 테스트 지침

## 핵심 행동 지침
1. **파서 라이브러리**: 본 프로젝트는 `ciscoconfparse2`를 단일 파서 표준으로 사용합니다. 레거시 파서로 회귀하지 않습니다.
2. **테스트 검증**: 코드 변경이나 기능 추가 시 반드시 `tests/test_audit_e2e_playwright.py` 및 `scratch/test_e2e_api.py`를 실행하여 회귀 버그가 없는지 확인합니다.
3. **100% 준수율 + Extra Config 탐지**: 골든 룰 통과 여부와 별개로, 타겟에 추가된 불필요/보안 위협 라인은 `extra_configs`로 탐지하고 롤백 명령어를 생성해야 합니다.
4. **보안 위협 우선순위**:
   - DANGER: 비인가 priv 15 계정, 취약 SNMP(RW, public), telnet, no switchport port-security, permit any any
   - WARNING: 미인가 라우팅(ospf, bgp), 정적 경로, 미인가 VRF
   - INFO: 일반 추가 라인
5. **롤백 스크립트 표준**: Cisco IOS/NX-OS CLI 문법에 부합하는 `configure terminal` ~ `end`, `write memory` 표준 블록 형식을 유지합니다.
