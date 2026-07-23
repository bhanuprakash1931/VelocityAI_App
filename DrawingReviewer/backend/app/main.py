import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
from uuid import uuid4
from typing import Optional

from .config import settings, get_api_key, get_base_url, get_model, set_runtime
from .models import Session, LlmConfigRequest, AnalyzeRequest, ReportRequest, ChatRequest
from . import store
from .services import run_analyze, run_report, run_chat

app = FastAPI(title="Velocity Drawing Reviewer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins="*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Config ────────────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    key = get_api_key()
    return {
        "openai_api_key": ("*" * 8 + key[-4:]) if len(key) > 8 else ("*" * len(key) if key else ""),
        "openai_base_url": get_base_url(),
        "openai_model": get_model(),
        "has_key": bool(key),
        "source": "runtime" if key and key != settings.openai_api_key else ("env" if settings.openai_api_key else "none"),
    }


@app.put("/api/config")
async def put_config(req: LlmConfigRequest):
    key = get_api_key() if req.openai_api_key.strip() == "__keep__" else req.openai_api_key
    set_runtime(key, req.openai_base_url, req.openai_model)
    import httpx as _httpx
    llm_mode = "demo"; llm_error = None
    key = get_api_key()
    if key:
        try:
            async with _httpx.AsyncClient(timeout=8) as c:
                r = await c.post(
                    get_base_url().rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": get_model(), "temperature": 0, "max_tokens": 1,
                          "messages": [{"role": "user", "content": "hi"}]}
                )
                llm_mode = "configured" if r.status_code in (200, 400) else "error"
                if r.status_code not in (200, 400):
                    llm_error = f"HTTP {r.status_code}"
        except _httpx.ConnectError as e:
            llm_mode = "unreachable"; llm_error = f"Cannot reach {get_base_url()}: {e}"
        except _httpx.TimeoutException:
            llm_mode = "unreachable"; llm_error = "Connection timed out"
        except Exception as e:
            llm_mode = "error"; llm_error = str(e)
    return {"success": True, "llm_mode": llm_mode, "llm_error": llm_error}


@app.get("/api/health")
async def health():
    llm_mode = "demo"; llm_error = None
    if settings.openai_api_key:
        import httpx as _httpx
        try:
            async with _httpx.AsyncClient(timeout=8) as c:
                r = await c.post(
                    settings.openai_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}",
                             "Content-Type": "application/json"},
                    json={"model": settings.openai_model, "temperature": 0, "max_tokens": 1,
                          "messages": [{"role": "user", "content": "hi"}]}
                )
                if r.status_code in (200, 400):
                    llm_mode = "configured"
                else:
                    llm_mode = "error"; llm_error = f"HTTP {r.status_code}"
        except Exception as e:
            llm_mode = "unreachable"; llm_error = str(e)
    return {"status": "healthy", "llm_mode": llm_mode, "llm_url": settings.openai_base_url,
            "llm_model": settings.openai_model, "llm_error": llm_error}


# ── Sessions ──────────────────────────────────────────────────────────────

@app.get("/api/sessions")
def sessions():
    return store.list_all()


@app.post("/api/sessions")
def create():
    s = Session(id=str(uuid4()), title="New Drawing Review Session")
    store.save(s)
    return s


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    try:
        return store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found")


@app.delete("/api/sessions/{sid}")
def delete_session(sid: str):
    store.delete(sid)
    return {"success": True}


# ── Upload ────────────────────────────────────────────────────────────────

@app.post("/api/sessions/{sid}/upload/drawing")
async def upload_drawing(sid: str, file: UploadFile = File(...)):
    s = get_session(sid)
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF drawings are accepted.")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File too large")
    dest_dir = settings.data_dir / "uploads" / sid
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (Path(file.filename).name)
    dest.write_bytes(data)
    if str(dest) not in s.drawing_paths:
        s.drawing_paths.append(str(dest))
    store.save(s)
    return {"success": True, "file": file.filename, "file_path": str(dest)}


@app.post("/api/sessions/{sid}/upload/template")
async def upload_template(sid: str, file: UploadFile = File(...)):
    s = get_session(sid)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        raise HTTPException(400, "Only .xlsx or .xlsm templates are accepted.")
    data = await file.read()
    dest_dir = settings.data_dir / "uploads" / sid
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / Path(file.filename).name
    dest.write_bytes(data)
    s.template_path = str(dest)
    store.save(s)
    return {"success": True, "file": file.filename, "template_path": str(dest)}


# ── Analyze ───────────────────────────────────────────────────────────────

@app.post("/api/sessions/{sid}/analyze")
async def analyze(sid: str, req: AnalyzeRequest):
    s = get_session(sid)
    paths = req.drawing_paths or s.drawing_paths
    if not paths:
        raise HTTPException(400, "No drawing PDFs attached. Upload a drawing first.")
    try:
        result = await run_analyze(paths, req.best_practices)
    except Exception as e:
        logging.exception("Analysis failed")
        raise HTTPException(500, f"Analysis failed: {e}")
    s.drawing_paths = paths
    s.extracted_data = result.get("extracted_data", {})
    s.check_results = result.get("check_results", {})
    s.analysis_done = True
    title_block = s.extracted_data.get("title_block") or {}
    dn = (title_block.get("drawing_number") or title_block.get("title") or "") if isinstance(title_block, dict) else ""
    if dn:
        s.title = f"Review: {dn}"
    store.save(s)
    findings = s.check_results.get("findings", [])
    return {
        "success": True,
        "stage": "analysis_complete",
        "page_count": result.get("page_count", 0),
        "findings_count": len(findings),
        "extracted_data": s.extracted_data,
        "check_results": s.check_results,
    }


# ── Report ────────────────────────────────────────────────────────────────

@app.post("/api/sessions/{sid}/report")
async def report(sid: str, req: ReportRequest):
    s = get_session(sid)
    paths = req.drawing_paths or s.drawing_paths
    template = req.template_path or s.template_path
    if not s.analysis_done:
        if not paths:
            raise HTTPException(400, "No drawing PDFs attached.")
        try:
            result = await run_analyze(paths, req.best_practices)
        except Exception as e:
            raise HTTPException(500, f"Analysis failed: {e}")
        s.drawing_paths = paths
        s.extracted_data = result.get("extracted_data", {})
        s.check_results = result.get("check_results", {})
        s.analysis_done = True
    try:
        rpt = await run_report(
            drawing_paths=s.drawing_paths,
            extracted_data=s.extracted_data,
            check_results=s.check_results,
            template_path=template,
            best_practices=req.best_practices,
        )
    except Exception as e:
        logging.exception("Report generation failed")
        raise HTTPException(500, f"Report generation failed: {e}")
    s.report_sections = rpt.get("report_sections", {})
    s.report_checklist = rpt.get("report_checklist", [])
    s.report_preview_html = rpt.get("report_preview_html", "")
    s.report_docx_path = rpt.get("report_docx_path", "")
    s.report_pdf_path = rpt.get("report_pdf_path", "")
    s.filled_checklist_path = rpt.get("filled_checklist_path", "")
    s.filled_checklist_preview_html = rpt.get("filled_checklist_preview_html", "")
    s.report_done = True
    store.save(s)
    return {
        "success": True,
        "stage": "complete",
        "report_preview_html": s.report_preview_html,
        "report_docx_path": s.report_docx_path,
        "report_pdf_path": s.report_pdf_path,
        "filled_checklist_path": s.filled_checklist_path,
        "filled_checklist_preview_html": s.filled_checklist_preview_html,
        "report_checklist": s.report_checklist,
    }


# ── Chat ──────────────────────────────────────────────────────────────────

@app.post("/api/sessions/{sid}/chat")
async def chat(sid: str, req: ChatRequest):
    s = get_session(sid)
    s.messages.append({"role": "user", "content": req.message})
    try:
        response = await run_chat(
            message=req.message,
            extracted_data=s.extracted_data,
            check_results=s.check_results,
            report_sections=s.report_sections,
            report_checklist=s.report_checklist,
            chat_history=req.chat_history,
        )
    except Exception as e:
        response = f"Chat error: {e}"
    s.messages.append({"role": "assistant", "content": response})
    store.save(s)
    return {"success": True, "response": response}


# ── Download ──────────────────────────────────────────────────────────────

@app.get("/api/download")
def download(path: str):
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path=str(p), filename=p.name, media_type="application/octet-stream")