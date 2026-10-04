# Network Config Auditor — 프로젝트 지침 및 AI 상시 참조 가이드

이 문서는 AI 어시스턴트(LLM)가 본 프로젝트에서 작업할 때 항상 기본 컨텍스트로 준수해야 하는 핵심 아키텍처 원칙, 코딩 컨벤션 및 **필수 테스트 체크리스트**입니다.

---

## 1. 핵심 아키텍처 및 기술 스택 원칙
- **파서 엔진**: 반드시 `ciscoconfparse2` 라이브러리를 기반으로 계층 파싱 및 트리 구성을 수행합니다 (`CiscoConfParse`).
- **테스트 환경**:
  - `playwright` 및 `pytest-playwright`를 메인 E2E/통합 테스트 프레임워크로 사용합니다.
  - VSCode Test Explorer 및 CLI(`uv run pytest tests/test_audit_e2e_playwright.py`) 모두에서 원클릭으로 구동 가능하도록 테스트 환경을 유지합니다.
- **코드 보호**: 기능 변경 및 주요 리팩토링 시 항상 별도 git feature 브랜치를 분기하여 작업합니다.

---

## 2. 골든 컨피그 감사 & Diff/롤백 핵심 규칙
- **침묵형 위협 감지 (100% 준수율 상황)**:
  - 타겟 장비가 골든 룰을 100% 만족하더라도, 기준 템플릿에 없는 추가 라인이 있을 경우 반드시 `extra_configs`로 감지(Diff)해야 합니다.
- **보안 위험도 분류**:
  - `DANGER`: 비인가 Privilege 15 계정, 취약 SNMP 커뮤니티(RW, public), Telnet 허용, 보안 기능 무력화(`no switchport port-security` 등), `permit any any` 전면 허용 ACL
  - `WARNING`: 비인가 라우팅 프로토콜, 비인가 정적 라우트, 비인가 VRF, 불필요 서비스
  - `INFO`: 일반 추가 설정
- **스마트 롤백 CLI 생성**:
  - 블록 전체 추가: 최상위에서 `no <block>` 처리 (예: `no router ospf 99`)
  - 블록 내 라인 추가: 부모 컨텍스트 진입 후 `no <cmd>` 처리
  - 보안 해제 역명령: 이미 `no`로 되어 있던 설정은 `no`를 제거하여 원상 복구 (예: `switchport port-security`)
  - 스크립트 완결성: `configure terminal`로 시작하여 `end` 및 `write memory`로 완결

---

## 3. 릴리즈 및 코드 수정 시 필수 테스트 체크리스트

모든 코드 수정, 새 룰 추가 또는 릴리즈 전 반드시 아래 6대 검증 항목을 통과해야 합니다.

### [1] 구문 파싱 및 노이즈 필터링 (Parsing & Sanitization)
- [ ] `show running-config` 프롬프트, 터미널 로그, 세션 배너 등 비설정 노이즈가 자동 정제되는가?
- [ ] L2 포트(스위치포트)와 L3 포트(라우티드/SVI/서브인터페이스)가 정확히 분리 그룹화되는가?
- [ ] `banner motd ^C ... ^C` 등 다중 라인 특수 배너가 깨짐 없이 보존되는가?
- [ ] `samples/` 폴더 내 실제 장비 설정 파일들(`test_parse.py samples`) 검증이 100% 통과하는가?

### [2] 골든 룰 매칭 및 정규화 (Compliance Engine)
- [ ] 다중 공백, 탭, 인터페이스 축약형(`Gi` vs `GigabitEthernet`), 대소문자 차이로 인한 오탐(False Fail)이 없는가?
- [ ] `exact`, `contains`, `regex`, `exists` 매칭 타입이 사양대로 판정되는가?
- [ ] 호스트명 정규식(`conditional_rules`) 기반 동적 룰 주입이 정상 동작하는가?

### [3] Diff 엔진 & 미인가 추가 설정 탐지 (Extra Config Detection)
- [ ] 골든 준수율이 100%일 때도 기준에 없는 추가 라인이 `extra_configs`로 누락 없이 추출되는가?
- [ ] 블록 전체 추가(`is_block_extra`)와 블록 내 명령어 추가가 명확히 구분되는가?

### [4] 보안 위협도 자동 분류 (Security Threat Classification)
- [ ] 비인가 관리자 계정, SNMP RW 커뮤니티, 보안 무력화 명령이 `DANGER`로 분류되는가?
- [ ] 각 추가 설정마다 한글 위험 사유(`risk_reason`)와 권장 조치가 올바르게 매핑되는가?

### [5] 롤백 CLI 스크립트 및 Clean Config 무결성 (Remediation)
- [ ] 개별 라인 롤백 명령어(`rollback_cmd`)가 올바른 Cisco 문법으로 생성되는가?
- [ ] 전체 통합 롤백 스크립트(`rollback_script`)가 중복 없이 블록별로 그룹화되는가?
- [ ] Clean Config 다운로드 시 추가 라인만 `! [REMOVED_BY_AUDITOR]`로 주석 처리되고 기존 설정이 보존되는가?

### [6] Playwright E2E UI 자동화 테스트
- [ ] 아래 명령어로 브라우저 E2E 테스트가 오류 없이 통과하는가?
  ```bash
  uv run pytest tests/test_audit_e2e_playwright.py -v
  ```
- [ ] 결과 드로어에서 `골든 룰 점검`, `추가된 설정 Diff`, `롤백 CLI 스크립트` 3개 탭 전환 및 복사/다운로드 인터랙션이 정상 동작하는가?
