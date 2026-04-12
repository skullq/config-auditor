"""
core/llm.py
Ollama LLM 연동 — 비교 결과를 정규화된 레포트로 변환.
"""

import httpx
import json
from typing import AsyncIterator

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_PROMPT_TEMPLATE = """당신은 네트워크 설정 감사(Audit) 데이터 정교화 및 정규화 전문가입니다.

입력 데이터는 골든 컨피그와 실제 장비 설정을 비교한 구조화된 결과(JSON)입니다. 당신의 목표는 이 결과를 바탕으로 엔지니어가 비즈니스 관점에서 즉각적으로 이해하고 조치할 수 있도록 보고서를 '정제(Refine)'하고 '풍성하게(Enrich)' 하는 것입니다.

## 입력 데이터 정보
- Hostname: {hostname}
- 적용 템플릿: {template_name}
- 전체 판정/점수: {overall} ({score}%)

## 상세 비교 결과 (Pre-processed)
{items_summary}

## 보고서 작성 가이드라인 (중요)
1. **정규화**: 불필요한 기술적 나열보다는 "어떤 보안 정책이 위반되었는지", "어떤 표준 운영 절차가 누락되었는지"를 중심으로 정규화된 요약을 작성하세요.
2. **분석 심화**: 특히 Review/Fail 항목에 대해, 이것이 네트워크 성능, 보안, 또는 관리 용이성에 미치는 구체적인 영향(Impact)을 기술하세요.
3. **조치 로드맵**: 단순히 "수정하세요"가 아닌, 실제 설정 명령어를 포함한 단계별 권고사항을 제시하세요.
4. **결과 가공**: 기존 데이터를 그대로 복사하지 말고, 전문가의 시각으로 재해석하여 한 단계 업그레이드된 레포트를 마크다운 형식으로 작성하세요.
"""


async def get_ollama_models(base_url: str = DEFAULT_OLLAMA_URL) -> list[str]:
    """Ollama에서 사용 가능한 모델 목록 조회."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{base_url}/api/tags")
            r.raise_for_status()
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


async def check_ollama_available(base_url: str = DEFAULT_OLLAMA_URL) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{base_url}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


def _build_items_summary(compare_result: dict) -> str:
    lines = []
    for item in compare_result.get("items", []):
        status_emoji = {"pass": "✅", "review": "⚠️", "fail": "❌"}.get(item["status"], "?")
        lines.append(
            f"{status_emoji} [{item['status'].upper()}] {item['label']}\n"
            f"   - 기대값: {item['expected']}\n"
            f"   - 실제값: {item['actual']}\n"
            f"   - 메시지: {item['message']}"
        )
    return '\n\n'.join(lines)


async def generate_report(
    compare_result: dict,
    hostname: str,
    template_name: str,
    base_url: str = DEFAULT_OLLAMA_URL,
    model: str = "llama3",
    prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
) -> str:
    """
    비교 결과를 Ollama LLM에 전달하여 레포트 생성.
    스트리밍을 사용하여 전체 텍스트를 반환.
    """
    items_summary = _build_items_summary(compare_result)
    prompt = prompt_template.format(
        hostname=hostname,
        template_name=template_name,
        overall=compare_result.get("overall", "N/A"),
        score=compare_result.get("score", 0),
        items_summary=items_summary,
    )

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{base_url}/api/generate", json=payload)
        r.raise_for_status()
        data = r.json()
        return data.get("response", "")


async def generate_report_stream(
    compare_result: dict,
    hostname: str,
    template_name: str,
    base_url: str = DEFAULT_OLLAMA_URL,
    model: str = "llama3",
    prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
) -> AsyncIterator[str]:
    """
    비교 결과를 Ollama LLM에 전달하여 레포트 생성 (스트리밍).
    SSE 포맷으로 텍스트를 응답.
    """
    items_summary = _build_items_summary(compare_result)
    prompt = prompt_template.format(
        hostname=hostname,
        template_name=template_name,
        overall=compare_result.get("overall", "N/A"),
        score=compare_result.get("score", 0),
        items_summary=items_summary,
    )

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            async with client.stream("POST", f"{base_url}/api/generate", json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if line:
                        try:
                            # Ollama returns one JSON object per line when stream=True
                            data = json.loads(line)
                            chunk = data.get("response", "")
                            if chunk:
                                # yield SSE format
                                yield f"data: {json.dumps({'text': chunk})}\n\n"
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
             yield f"data: {json.dumps({'error': str(e)})}\n\n"

    yield "data: [DONE]\n\n"

def generate_basic_report(
    compare_result: dict,
    hostname: str,
    template_name: str,
) -> str:
    """
    Ollama 없을 때 자체 생성하는 기본 텍스트 레포트.
    """
    overall = compare_result.get("overall", "N/A")
    score = compare_result.get("score", 0)
    items = compare_result.get("items", [])

    fails = [i for i in items if i["status"] == "fail"]
    reviews = [i for i in items if i["status"] == "review"]
    passes = [i for i in items if i["status"] == "pass"]

    lines = [
        f"# 설정 감사 보고서",
        f"",
        f"| 항목 | 내용 |",
        f"|------|------|",
        f"| Hostname | `{hostname}` |",
        f"| 적용 템플릿 | {template_name} |",
        f"| **전체 판정** | **{overall}** |",
        f"| 점수 | {score}% ({compare_result.get('passed_items',0)}/{compare_result.get('total_items',0)}) |",
        f"",
    ]

    if fails:
        lines += [f"## ❌ Fail 항목 ({len(fails)}개)", ""]
        for item in fails:
            lines.append(f"- **{item['label']}**")
            lines.append(f"  - 기대값: `{item['expected']}`")
            lines.append(f"  - 실제값: `{item['actual']}`")
            lines.append(f"  - 조치: 해당 설정을 추가/수정하세요.")
            lines.append("")

    if reviews:
        lines += [f"## ⚠️ Review 항목 ({len(reviews)}개)", ""]
        for item in reviews:
            lines.append(f"- **{item['label']}**")
            lines.append(f"  - 기대값: `{item['expected']}`")
            lines.append(f"  - 실제값: `{item['actual']}`")
            lines.append("")

    if passes:
        lines += [f"## ✅ Pass 항목 ({len(passes)}개)", ""]
        for item in passes:
            lines.append(f"- {item['label']}")
        lines.append("")

    return '\n'.join(lines)
