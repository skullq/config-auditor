"""
main.py — FastAPI 앱 진입점
"""

import uuid
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

# venv 경로 인식
sys.path.insert(0, str(Path(__file__).parent))

from db.database import (
    init_db, save_template, list_templates, get_template, delete_template,
    save_compare_result, list_compare_results, get_compare_result,
    get_setting, set_setting,
)
from core.parser import parse_config, flatten_for_ui
from core.comparator import compare, match_template
from core.llm import (
    get_ollama_models, check_ollama_available,
    generate_report, generate_basic_report,
    DEFAULT_PROMPT_TEMPLATE,
)

# ── App Init ───────────────────────────────────────────────────────────
app = FastAPI(title="Network Config Auditor", version="1.0.0")
init_db()

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


# ── Root ───────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# ════════════════════════════════════════════════════════════════════════
# GOLDEN CONFIG API
# ════════════════════════════════════════════════════════════════════════

@app.post("/api/golden/upload")
async def golden_upload(file: UploadFile = File(...), os: str = "iosxe"):
    """설정 파일 업로드 → Genie 분석 → UI 항목 목록 반환."""
    content = (await file.read()).decode("utf-8", errors="replace")
    parsed = parse_config(content, os_type=os)
    ui_items = flatten_for_ui(parsed)
    return {
        "hostname": parsed.get("hostname"),
        "os": parsed.get("os"),
        "section_count": len(parsed.get("sections", {})),
        "items": ui_items,
        "parsed": parsed,  # 저장용 원본
    }


class SaveTemplateRequest(BaseModel):
    name: str
    hostname_regex: str = ""
    description: str = ""
    os_type: str = "iosxe"
    selected_items: list[dict]
    conditional_rules: list[dict] = []
    golden_parsed: dict


@app.post("/api/golden/save")
async def golden_save(req: SaveTemplateRequest):
    tid = save_template(
        name=req.name,
        hostname_regex=req.hostname_regex,
        description=req.description,
        os_type=req.os_type,
        golden_items=req.selected_items,
        conditional_rules=req.conditional_rules,
        golden_parsed=req.golden_parsed,
    )
    return {"template_id": tid, "message": "저장 완료"}


@app.get("/api/golden/templates")
async def golden_list():
    return list_templates()


@app.get("/api/golden/templates/{tid}")
async def golden_get(tid: str):
    tpl = get_template(tid)
    if not tpl:
        raise HTTPException(404, "템플릿을 찾을 수 없습니다.")
    return tpl


@app.delete("/api/golden/templates/{tid}")
async def golden_delete(tid: str):
    delete_template(tid)
    return {"message": "삭제 완료"}


# ════════════════════════════════════════════════════════════════════════
# COMPARE API
# ════════════════════════════════════════════════════════════════════════

@app.post("/api/compare/upload")
async def compare_upload(file: UploadFile = File(...), os: str = "iosxe"):
    """파일 업로드 → 파싱 + 자동 템플릿 매칭."""
    content = (await file.read()).decode("utf-8", errors="replace")
    parsed = parse_config(content, os_type=os)
    hostname = parsed.get("hostname") or ""

    # 자동 매칭
    templates = list_templates()
    matched = None
    for tpl_meta in templates:
        tpl = get_template(tpl_meta["id"])
        if tpl:
            result = match_template(hostname, [tpl])
            # OS가 일치하거나 템플릿의 OS가 기본값인 경우 매칭 (단순화)
            if result and tpl.get("os", "iosxe") == os:
                matched = tpl_meta
                break

    return {
        "hostname": hostname,
        "os": os,
        "parsed": parsed,
        "matched_template": matched,
        "all_templates": templates,
    }


class RunCompareRequest(BaseModel):
    parsed: dict
    template_id: str
    save: bool = True


@app.post("/api/compare/run")
async def compare_run(req: RunCompareRequest):
    tpl = get_template(req.template_id)
    if not tpl:
        raise HTTPException(404, "템플릿을 찾을 수 없습니다.")

    result = compare(tpl["golden_items"], req.parsed, tpl.get("conditional_rules", []))
    hostname = req.parsed.get("hostname", "unknown")

    if req.save:
        save_compare_result(
            hostname=hostname,
            template_id=req.template_id,
            template_name=tpl["name"],
            overall=result["overall"],
            score=result["score"],
            detail=result,
        )

    return {
        "hostname": hostname,
        "template_name": tpl["name"],
        **result,
    }


@app.get("/api/compare/results")
async def compare_results_list():
    return list_compare_results()


@app.get("/api/compare/results/{rid}")
async def compare_result_get(rid: str):
    r = get_compare_result(rid)
    if not r:
        raise HTTPException(404)
    return r


# ════════════════════════════════════════════════════════════════════════
# BULK API
# ════════════════════════════════════════════════════════════════════════

@app.post("/api/bulk/upload")
async def bulk_upload(files: list[UploadFile] = File(...)):
    """여러 파일 업로드 → 자동 매칭 + 비교 일괄 처리."""
    job_id = str(uuid.uuid4())
    templates_meta = list_templates()
    templates_full = [get_template(t["id"]) for t in templates_meta]
    templates_full = [t for t in templates_full if t]

    results = []
    for file in files:
        content = (await file.read()).decode("utf-8", errors="replace")
        parsed = parse_config(content)
        hostname = parsed.get("hostname") or file.filename or "unknown"

        matched_tpl = match_template(hostname, templates_full)
        if not matched_tpl:
            results.append({
                "filename": file.filename,
                "hostname": hostname,
                "overall": "Skipped",
                "score": None,
                "message": "매칭되는 템플릿 없음",
                "result_id": None,
            })
            continue

        cmp_result = compare(matched_tpl["golden_items"], parsed, matched_tpl.get("conditional_rules", []))
        rid = save_compare_result(
            hostname=hostname,
            template_id=matched_tpl["id"],
            template_name=matched_tpl["name"],
            overall=cmp_result["overall"],
            score=cmp_result["score"],
            detail=cmp_result,
            bulk_job_id=job_id,
        )
        results.append({
            "filename": file.filename,
            "hostname": hostname,
            "template_name": matched_tpl["name"],
            "overall": cmp_result["overall"],
            "score": cmp_result["score"],
            "result_id": rid,
        })

    return {"job_id": job_id, "results": results}


@app.get("/api/bulk/results/{job_id}")
async def bulk_results(job_id: str):
    return list_compare_results(bulk_job_id=job_id)


@app.get("/api/bulk/results/{job_id}/export")
async def bulk_export(job_id: str):
    """CSV 다운로드."""
    rows = list_compare_results(bulk_job_id=job_id)
    lines = ["hostname,template,overall,score,date"]
    for r in rows:
        lines.append(
            f"{r['hostname']},{r['template_name']},{r['overall']},{r['score']},{r['created_at']}"
        )
    csv_content = '\n'.join(lines)

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=bulk_{job_id[:8]}.csv"},
    )


# ════════════════════════════════════════════════════════════════════════
# LLM / REPORT API
# ════════════════════════════════════════════════════════════════════════

@app.get("/api/llm/models")
async def llm_models():
    base_url = get_setting("ollama_url", "http://localhost:11434")
    available = await check_ollama_available(base_url)
    if not available:
        return {"available": False, "models": []}
    models = await get_ollama_models(base_url)
    return {"available": True, "models": models}


class LLMSettingsRequest(BaseModel):
    ollama_url: str = "http://localhost:11434"
    model: str = "llama3"
    prompt_template: str = DEFAULT_PROMPT_TEMPLATE


@app.post("/api/llm/settings")
async def llm_settings_save(req: LLMSettingsRequest):
    set_setting("ollama_url", req.ollama_url)
    set_setting("ollama_model", req.model)
    set_setting("prompt_template", req.prompt_template)
    return {"message": "설정 저장 완료"}


@app.get("/api/llm/settings")
async def llm_settings_get():
    return {
        "ollama_url": get_setting("ollama_url", "http://localhost:11434"),
        "model": get_setting("ollama_model", "llama3"),
        "prompt_template": get_setting("prompt_template", DEFAULT_PROMPT_TEMPLATE),
    }


class GenerateReportRequest(BaseModel):
    result_id: str
    use_llm: bool = False


@app.post("/api/llm/report")
async def llm_report(req: GenerateReportRequest):
    r = get_compare_result(req.result_id)
    if not r:
        raise HTTPException(404, "비교 결과를 찾을 수 없습니다.")

    hostname = r.get("hostname", "unknown")
    template_name = r.get("template_name", "unknown")
    compare_result = r.get("detail", {})

    if req.use_llm:
        base_url = get_setting("ollama_url", "http://localhost:11434")
        model = get_setting("ollama_model", "llama3")
        prompt_template = get_setting("prompt_template", DEFAULT_PROMPT_TEMPLATE)
        try:
            report = await generate_report(
                compare_result, hostname, template_name,
                base_url=base_url, model=model, prompt_template=prompt_template,
            )
        except Exception as e:
            report = generate_basic_report(compare_result, hostname, template_name)
            report += f"\n\n> ⚠️ LLM 오류 ({e}), 기본 레포트 사용"
    else:
        report = generate_basic_report(compare_result, hostname, template_name)

    return {"report": report, "hostname": hostname}
