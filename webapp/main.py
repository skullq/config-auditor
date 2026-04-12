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
    """설정 파일 업로드 → Genie 분석 → UI 항목 목록 반환. 인터페이스 섹션은 제외."""
    content = (await file.read()).decode("utf-8", errors="replace")
    parsed = parse_config(content, os_type=os)
    ui_items = [i for i in flatten_for_ui(parsed) if not i.get("section", "").startswith("interface")]
    return {
        "hostname": parsed.get("hostname"),
        "os": parsed.get("os"),
        "section_count": len(parsed.get("sections", {})),
        "items": ui_items,
        "parsed": parsed,
    }


@app.post("/api/golden/upload-interface")
async def golden_upload_interface(file: UploadFile = File(...), os: str = "auto"):
    """인터페이스 전용 설정 파일 업로드 → 인터페이스 블록 파싱 → 업링크/L2 분류."""
    from core.interface_parser import parse_interfaces, flatten_interfaces_for_ui
    content = (await file.read()).decode("utf-8", errors="replace")
    interfaces = parse_interfaces(content)
    uplinks = [i for i in interfaces if i["type"] == "uplink"]
    l2_ports = [i for i in interfaces if i["type"] == "l2"]
    ui_items = flatten_interfaces_for_ui(interfaces)
    return {
        "total": len(interfaces),
        "uplink_count": len(uplinks),
        "l2_count": len(l2_ports),
        "interfaces": interfaces,
        "items": ui_items,
    }


class SaveTemplateRequest(BaseModel):
    name: str
    hostname_regex: str = ""
    description: str = ""
    os_type: str = "iosxe"
    selected_items: list[dict]
    conditional_rules: list[dict] = []
    golden_parsed: dict
    template_id: Optional[str] = None


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
        template_id=req.template_id,
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

    rid = None
    if req.save:
        rid = save_compare_result(
            hostname=hostname,
            template_id=req.template_id,
            template_name=tpl["name"],
            overall=result["overall"],
            score=result["score"],
            detail=result,
        )

    return {
        "id": rid,
        "hostname": hostname,
        "template_name": tpl["name"],
        **result,
    }


@app.get("/api/compare/results")
async def compare_results_list():
    return list_compare_results()

@app.delete("/api/compare/results/{rid}")
async def compare_result_delete(rid: str):
    from db.database import delete_compare_result
    delete_compare_result(rid)
    # Delete report file if exists
    report_file = REPORT_DIR / f"{rid}.md"
    if report_file.exists():
        report_file.unlink()
    return {"message": "삭제 완료"}

@app.get("/api/compare/download/{rid}")
async def compare_result_download(rid: str):
    r = get_compare_result(rid)
    if not r:
        raise HTTPException(404, "결과를 찾을 수 없습니다.")
    import json
    return StreamingResponse(
        iter([json.dumps(r, ensure_ascii=False, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=compare_{r['hostname']}_{rid[:8]}.json"}
    )


@app.get("/api/compare/results/{rid}")
async def compare_result_get(rid: str):
    r = get_compare_result(rid)
    if not r:
        raise HTTPException(404)
    return r


@app.get("/api/compare/check_duplicate")
async def compare_check_duplicate(hostname: str):
    results = list_compare_results()
    for r in results:
        if r["hostname"] == hostname:
            return {"exists": True, "result_id": r["id"]}
    return {"exists": False}


# ════════════════════════════════════════════════════════════════════════
# REPORT & LLM API
# ════════════════════════════════════════════════════════════════════════

REPORT_DIR = Path(__file__).parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)

@app.get("/api/reports/list")
async def list_reports_api():
    """DB의 Compare 이력과 저장된 Report 파일을 조합하여 반환"""
    results = list_compare_results()
    for r in results:
        report_file = REPORT_DIR / f"{r['id']}.md"
        r["has_report"] = report_file.exists()
    return results

@app.delete("/api/reports/duplicates")
async def delete_duplicate_reports():
    """호스트명 기준 최신 내역 1건만 남기고 중복된 과거 내역을 일괄 삭제합니다."""
    results = list_compare_results()
    seen = set()
    deleted = 0
    from db.database import delete_compare_result
    
    for r in results:
        hostname = r["hostname"]
        if hostname in seen:
            rid = r["id"]
            delete_compare_result(rid)
            report_file = REPORT_DIR / f"{rid}.md"
            if report_file.exists():
                report_file.unlink()
            deleted += 1
        else:
            seen.add(hostname)
            
    return {"message": f"중복 내역 {deleted}건이 삭제되었습니다.", "deleted_count": deleted}

@app.get("/api/reports/download/{rid}")
async def download_report(rid: str):
    report_file = REPORT_DIR / f"{rid}.md"
    if not report_file.exists():
        raise HTTPException(404, "레포트 파일이 없습니다.")
    return StreamingResponse(
        open(report_file, "rb"),
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=report_{rid[:8]}.md"}
    )


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

from db.database import reset_db_data

@app.post("/api/settings/reset")
async def wipe_database_api():
    reset_db_data()
    return {"message": "데이터가 모두 초기화되었습니다."}


class GenerateReportRequest(BaseModel):
    result_id: str
    use_llm: bool = False


@app.post("/api/llm/report")
async def llm_report_basic(req: GenerateReportRequest):
    r = get_compare_result(req.result_id)
    if not r:
        raise HTTPException(404, "비교 결과를 찾을 수 없습니다.")

    hostname = r.get("hostname", "unknown")
    template_name = r.get("template_name", "unknown")
    compare_result = r.get("detail", {})

    report = generate_basic_report(compare_result, hostname, template_name)
    report_file = REPORT_DIR / f"{req.result_id}.md"
    report_file.write_text(report, encoding="utf-8")
    
    return {"message": "기본 레포트 생성 완료", "hostname": hostname}


from core.llm import generate_report_stream
import json

@app.get("/api/llm/report/stream/{result_id}")
async def llm_report_stream(result_id: str):
    r = get_compare_result(result_id)
    if not r:
        raise HTTPException(404, "비교 결과를 찾을 수 없습니다.")

    hostname = r.get("hostname", "unknown")
    template_name = r.get("template_name", "unknown")
    compare_result = r.get("detail", {})

    base_url = get_setting("ollama_url", "http://localhost:11434")
    model = get_setting("ollama_model", "llama3")
    prompt_template = get_setting("prompt_template", DEFAULT_PROMPT_TEMPLATE)

    async def stream_and_save():
        full_text = ""
        # 0. 연결 확인용 첫 패킷 (JS에서 연결 성공을 즉시 알 수 있게 함)
        yield f"data: {json.dumps({'debug': 'Stream connected'})}\n\n"
        
        try:
            async for chunk_sse in generate_report_stream(
                compare_result, hostname, template_name,
                base_url=base_url, model=model, prompt_template=prompt_template
            ):
                if chunk_sse.startswith("data: "):
                    content = chunk_sse[6:].rstrip('\r\n')
                    if content and content != "[DONE]":
                        try:
                            parsed = json.loads(content)
                            if "text" in parsed:
                                full_text += parsed["text"]
                        except: pass
                yield chunk_sse
        except Exception as e:
            error_msg = f"data: {json.dumps({'error': str(e)})}\n\n"
            yield error_msg
        finally:
            report_file = REPORT_DIR / f"{result_id}.md"
            if full_text:
                report_file.write_text(full_text, encoding="utf-8")
            else:
                # LLM이 아무것도 안 줬을 경우, 빈 파일로라도 저장하여 404 방지 및 기본 내용 구성
                from core.llm import generate_basic_report
                basic = generate_basic_report(compare_result, hostname, template_name)
                report_file.write_text(f"⚠️ LLM 분석 실패 (Ollama 확인 필요)\n\n{basic}", encoding="utf-8")

    return StreamingResponse(stream_and_save(), media_type="text/event-stream")
