# Network Config Auditor (FastAPI + Pyats Genie + Ollama)

Cisco IOS-XE, NX-OS, IOS-XR, AireOS (WLC) 및 IOS 설정 파일을 자동으로 분석하고, 골든 컨피그(Golden Config) 기반으로 규정 준수 여부를 감사(Audit)하는 전문 프로젝트입니다. PyATS Genie를 통한 구조화된 분석과 Ollama LLM을 이용한 지능형 레포트 정제 기능을 제공합니다.

---

## 핵심 기능

### 1. 멀티 플랫폼 및 지능형 골든 컨피그 관리
- **멀티 OS 지원**: IOS-XE, NX-OS, IOS-XR, AireOS(WLC), 클래식 IOS 장비를 모두 지원합니다.
- **자동 섹션 탐지**: IOS 설정의 들여쓰기 규칙을 분석하여 Interface, OSPF, BGP, ACL 등 모든 섹션을 자동으로 분류합니다.
- **시각적 그룹화**: 골든 탭과 비교 탭 모두에서 논리적 섹션별로 항목을 그룹화하며, 고유 아이콘(🔗 인터페이스, 📂 일반 설정)을 통해 가독성을 높였습니다.
- **일괄 항목 제어**: 섹션 그룹별 '전체 선택' 및 '전체 해제' 기능을 통해 템플릿 커스터마이징 효율을 극대화했습니다.

### 2. 강력한 비교 엔진 (Expert Audit)
- **최고 수준의 정규화(Extreme Normalization)**: 단순 공백 차이, 탭, 특수 공백, 대소문자 차이를 완전히 무시하여 불필요한 오탐(False Negative)을 제거합니다.
- **이중 폴백(Fallback) 매칭**: 특정 설정 블록이 이동되거나 가려진 경우에도, 동일 섹션 내 전역 검색을 수행하여 실제 설정 존재 여부를 정확히 판정합니다.
- **자동 줄바꿈(Word Wrap) 지원**: 매우 긴 설명(Description)이나 복잡한 ACL 문구도 화면 크기에 맞게 자동으로 줄바꿈되어 최적의 가독성을 제공합니다.

### 3. 지속적 이력 관리 및 상세 조회 (Archive Engine)
- **감사 아카이빙**: 모든 감사 실행 결과는 SQLite 데이터베이스에 영구 저장됩니다.
- **대화형 상세 결과 모달**: 'Report' 탭의 과거 이력을 클릭 한 번으로 불러와, 실시간 검사와 동일한 그룹화 UI로 상세 내역을 언제든 다시 검토할 수 있습니다.
- **유연한 워크플로우**: 실시간 비교(Compare 탭)와 장기적 감사 추적(Report 탭)을 분리하여 효율적인 관리 환경을 제공합니다.

### 4. 호스트명 기반 동적 액션 (Conditional Rules)
- **Regex 기반 매칭**: 장비의 호스트명을 정규표현식으로 분석합니다.
- **조건부 추가 검증**: 예: 호스트명이 `^SH-.*-AGG`와 일치할 때만 특정 인터페이스 설정이나 ACL이 추가로 포함되도록 하는 동식 액션을 로드합니다.

### 5. 멀티 티어 감사 결과 (Pass / Review / Fail)
- **Pass**: 모든 필수 및 선택 항목이 기대값과 일치.
- **Review**: 가중치가 낮은 선택적 항목이 불일치하거나 누락된 경우.
- **Fail**: 필수 설정이 누락되었거나 기대값과 다른 경우.

### 6. LLM 기반 결과 정교화 (Report Enrichment)
- **Ollama 연동**: 로컬 LLM을 사용하여 감사 결과를 전문가 수준으로 재가공합니다.
- **영향도 분석**: 위반 사항이 네트워크 인프라에 미치는 영향(Impact)을 스스로 분석하여 조치 로드맵을 제시합니다.

### 7. 유지보수 및 신뢰성
- **자동 데이터베이스 마이그레이션**: 시스템이 업데이트되어 새로운 스키마가 필요할 때, 별도의 설정 없이 시작 시 자동으로 DB 구조를 최신화하여 중단 없는 업그레이드를 보장합니다.

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
`uv`는 Rust로 작성된 초고속 파이썬 패키지 관리자입니다.
```bash
# 1. 가상환경 생성 및 패키지 동기화
# (pyproject.toml 또는 requirements.txt를 자동으로 감지합니다)
uv venv
source .venv/bin/activate  # 또는 .venv\Scripts\activate

# 2. 패키지 설치
uv pip install -r requirements.txt

# 3. 서버 실행
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

---

## 🗄 데이터베이스 설정 (SQLite)

본 프로젝트는 별도의 DB 서버 설치 없이 즉시 사용 가능한 **SQLite**를 사용합니다.

- **위치**: `webapp/data.db`에 파일 형태로 저장됩니다.
- **ORM**: SQLAlchemy를 통해 데이터 모델링 및 쿼리를 처리합니다.
- **주요 테이블**:
  - `templates`: 골든 컨피그 항목, 호스트명 Regex, 조건부 규칙 정의
  - `results`: 감사 수행 이력 및 상세 Pass/Fail 데이터
  - `settings`: Ollama URL, 사용 모델 등 시스템 설정값
---

## 📂 파일 및 템플릿 관리 위치

본 프로젝트의 모든 데이터는 프로젝트 폴더 내부에 로컬로 관리되어 외부 유출 위험이 적습니다.

1. **업로드된 설정 파일**:
   - 위치: `webapp/uploads/`
   - 설명: 비교 및 분석을 위해 브라우저를 통해 업로드된 임시 설정 파일들이 저장됩니다. `.gitignore`에 포함되어 있어 Git에는 저장되지 않습니다.

2. **골든 컨피그 템플릿**:
   - 위치: `webapp/data.db` (SQLite 내부)
   - 설명: 별도의 JSON/YAML 파일이 아닌, 데이터베이스의 `templates` 테이블에 직렬화되어 저장됩니다. 이를 통해 UI에서 편리하게 수정, 삭제 및 버전 관리를 할 수 있습니다.

3. **감사 결과 보고서**:
   - 위치: `webapp/data.db` (SQLite 내부)
   - 설명: 모든 감사 이력과 점수, 상세 불일치 결과는 DB에 저장되어 언제든 다시 조회할 수 있습니다.

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
