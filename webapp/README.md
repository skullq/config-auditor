# Network Config Auditor (FastAPI + Genie + Ollama)

Cisco IOS-XE, NX-OS, IOS-XR, AireOS (WLC) 및 IOS 설정 파일을 자동으로 분석하고, 골든 컨피그(Golden Config) 기반으로 규정 준수 여부를 감사(Audit)하는 전문 프로젝트입니다. PyATS Genie를 통한 구조화된 분석과 Ollama LLM을 이용한 지능형 레포트 정제 기능을 제공합니다.

---

## 핵심 기능

### 1. 멀티 플랫폼 및 지능형 골든 컨피그 관리
- 멀티 OS 지원: IOS-XE, NX-OS, IOS-XR, AireOS(WLC), 클래식 IOS 장비를 모두 지원합니다.
- 자동 섹션 탐지: IOS 설정의 들여쓰기 규칙을 분석하여 Interface, OSPF, BGP, ACL 등 모든 섹션을 자동으로 분류합니다.
- Genie 하이브리드 파싱: Genie 파서가 있는 섹션은 데이터 구조화(Dictionary)를, 없는 섹션은 Raw 텍스트로 보존하여 완벽한 분석을 지원합니다.
- 체크박스 기반 설계: 분석된 항목 중 감사에 포함할 항목을 UI에서 직접 선택하고 기대값(Expected Value)과 매칭 방식(Exact, Regex, Exists)을 설정합니다.

### 2. 호스트명 기반 동적 액션 (Conditional Rules)
- Regex 기반 매칭: 장비의 호스트명을 정규표현식으로 분석합니다.
- 조건부 추가 검증: 예: 호스트명이 ^SH-.*-AGG와 일치할 때만 특정 인터페이스 설정이나 ACL이 추가로 포함되도록 하는 동적 액션을 로드합니다.

### 3. 멀티 티어 감사 결과 (Pass / Review / Fail)
- Pass: 모든 필수 및 선택 항목이 기대값과 일치.
- Review: 가중치가 낮은 선택적 항목이 불일치하거나 누락된 경우.
- Fail: 필수 설정이 누락되었거나 기대값과 다른 경우.

### 4. 벌크(Bulk) 감사 대시보드
- 수백 개의 설정 파일을 동시에 업로드하여 일괄 감사를 수행합니다.
- 호스트명 패턴에 맞는 템플릿을 자동으로 매칭하며, 감사 결과를 CSV로 추출할 수 있습니다.

### 5. LLM 기반 결과 정교화 (Report Enrichment)
- Ollama 연동: 로컬 LLM을 사용하여 감사 결과를 전문가 수준으로 재가공합니다.
- 데이터 정규화: 비교 원본의 기술적 나열을 비즈니스 및 보안 관점의 표준 언어로 정규화합니다.
- 영향도 분석: 위반 사항이 네트워크 인프라에 미치는 영향(Impact)을 스스로 분석하여 조치 로드맵을 제시합니다.

---

## 기술 스택

- Backend: Python 3.12, FastAPI, Uvicorn
- Parsing: PyATS / Genie (Cisco Library)
- Storage: SQLite (SQLAlchemy)
- LLM: Ollama API (Local LLM)
- Frontend: Vanilla JS, CSS (Premium Dark Theme), HTML5

---

## 설치 및 실행

### 방법 1: uv 사용 (권장 - 빠름)
```bash
# 의존성 설치 및 실행을 한 번에
cd webapp
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

### 방법 2: pip 및 venv 사용
```bash
# 가상환경 생성 및 진입
python -m venv .venv
source .venv/bin/activate

# 필수 패키지 설치
cd webapp
pip install -r requirements.txt

# 서버 실행
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 3. Ollama 설치 (LLM 기능 사용 시)
```bash
# https://ollama.ai/ 에서 설치 후 모델 다운로드
ollama pull llama3  # 권장 모델
ollama serve
```

---

## 사용 방법

1. [Golden Tab]: 기준 설정 파일을 업로드하여 템플릿을 생성합니다. (호스트명별 동적 규칙 설정 가능)
2. [Compare Tab]: 감사 대상 파일을 업로드하여 결과를 확인합니다.
3. [Report Tab]: LLM 옵션을 사용하여 정제된 레포트를 생성하고 복사/다운로드합니다.
4. [Bulk Tab]: 전사 장비의 대규모 감사를 일괄 수행합니다.

---

## 프로젝트 구조

```
/webapp
├── main.py              # FastAPI 진입점 및 API 정의
├── core/
│   ├── parser.py        # Genie 파서 및 섹션 분리 로직
│   ├── comparator.py    # Pass/Review/Fail 비교 및 동적 액션 엔진
│   └── llm.py           # Ollama 프롬프트 및 레포트 정제 로직
├── db/
│   ├── database.py      # SQLite CRUD 및 설정 테이블 관리
├── static/              # 프론트엔드 자산 (Premium UI)
│   ├── index.html
│   ├── css/style.css
│   └── js/              # 리액티브 JS 모듈
└── data.db              # 로컬 데이터베이스
```

---

## 라이선스
Google DeepMind Advanced Agentic Coding 팀 - Antigravity 개발 가이드 준수.
