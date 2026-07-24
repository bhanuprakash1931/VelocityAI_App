"""
DrawingReviewer/backend/app/main.py
────────────────────────────────────
FastAPI application for the Drawing Reviewer.
Shared routes (config, health, sessions) are registered via common router factories.
"""
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path as FilePath
from uuid import uuid4

from .config import settings, get_api_key, get_base_url, get_model, set_runtime
from .models import Session, LlmConfigRequest, AnalyzeRequest, ReportRequest, ChatRequest
from . import store
from .services import run_analyze, run_report, run_chat

from common.backend.router import config_router, health_router, sessions_router, download_router
from common.backend.template_handler import save_upload

app = FastAPI(title='Velocity Drawing Reviewer API', version='1.0.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins='*',
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# ── Shared routes ─────────────────────────────────────────────────────────
app.include_router(config_router(
    get_api_key=get_api_key, get_base_url=get_base_url, get_model=get_model,
    set_runtime=set_runtime, settings=settings,
))
app.include_router(health_router(
    get_api_key=get_api_key, get_base_url=get_base_url, get_model=get_model,
    settings=settings,
))
app.include_router(sessions_router(
    store=store,
    session_factory=lambda: Session(id=str(uuid4()), title='New Drawing Review Session'),
))
app.include_router(download_router())


# ── Upload drawing ────────────────────────────────────────────────────────

@app.post('/api/sessions/{sid}/upload/drawing')
async def upload_drawing(sid: str, file: UploadFile = File(...)):
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    out, name = await save_upload(
        file=file,
        sid=sid,
        uploads_dir=settings.data_dir / 'uploads' / sid,
        max_upload_mb=settings.max_upload_mb,
        allowed_suffixes=frozenset({'pdf', '.pdf'}),
    )
    if str(out) not in s.drawing_paths:
        s.drawing_paths.append(str(out))
    store.save(s)
    return {'success': True, 'file': name, 'file_path': str(out)}


# ── Upload checklist template ─────────────────────────────────────────────

@app.post('/api/sessions/{sid}/upload/template')
async def upload_template(sid: str, file: UploadFile = File(...)):
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    out, name = await save_upload(
        file=file,
        sid=sid,
        uploads_dir=settings.data_dir / 'uploads' / sid,
        max_upload_mb=settings.max_upload_mb,
        allowed_suffixes=frozenset({'xlsx', '.xlsx', 'xlsm', '.xlsm'}),
    )
    s.template_path = str(out)
    store.save(s)
    return {'success': True, 'file': name, 'template_path': str(out)}


# ── Analyze ───────────────────────────────────────────────────────────────

@app.post('/api/sessions/{sid}/analyze')
async def analyze(sid: str, req: AnalyzeRequest):
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    paths = req.drawing_paths or s.drawing_paths
    if not paths:
        raise HTTPException(400, 'No drawing PDFs attached. Upload a drawing first.')
    try:
        result = await run_analyze(paths, req.best_practices)
    except Exception as e:
        logging.exception('Analysis failed')
        raise HTTPException(500, f'Analysis failed: {e}')
    s.drawing_paths = paths
    s.extracted_data = result.get('extracted_data', {})
    s.check_results = result.get('check_results', {})
    s.analysis_done = True
    title_block = s.extracted_data.get('title_block') or {}
    dn = (title_block.get('drawing_number') or title_block.get('title') or '') if isinstance(title_block, dict) else ''
    if dn:
        s.title = f'Review: {dn}'
    store.save(s)
    findings = s.check_results.get('findings', [])
    return {
        'success': True,
        'stage': 'analysis_complete',
        'page_count': result.get('page_count', 0),
        'findings_count': len(findings),
        'extracted_data': s.extracted_data,
        'check_results': s.check_results,
    }


# ── Report ────────────────────────────────────────────────────────────────

@app.post('/api/sessions/{sid}/report')
async def report(sid: str, req: ReportRequest):
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    paths = req.drawing_paths or s.drawing_paths
    template = req.template_path or s.template_path
    if not s.analysis_done:
        if not paths:
            raise HTTPException(400, 'No drawing PDFs attached.')
        try:
            result = await run_analyze(paths, req.best_practices)
        except Exception as e:
            raise HTTPException(500, f'Analysis failed: {e}')
        s.drawing_paths = paths
        s.extracted_data = result.get('extracted_data', {})
        s.check_results = result.get('check_results', {})
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
        logging.exception('Report generation failed')
        raise HTTPException(500, f'Report generation failed: {e}')
    s.report_sections          = rpt.get('report_sections', {})
    s.report_checklist         = rpt.get('report_checklist', [])
    s.report_preview_html      = rpt.get('report_preview_html', ''
    )
    s.report_docx_path         = rpt.get('report_docx_path', ''
    )
    s.report_pdf_path          = rpt.get('report_pdf_path', ''
    )
    s.filled_checklist_path    = rpt.get('filled_checklist_path', ''
    )
    s.filled_checklist_preview_html = rpt.get('filled_checklist_preview_html', ''
    )
    s.report_done = True
    store.save(s)
    return {
        'success': True,
        'stage': 'complete',
        'report_preview_html': s.report_preview_html,
        'report_docx_path': s.report_docx_path,
        'report_pdf_path': s.report_pdf_path,
        'filled_checklist_path': s.filled_checklist_path,
        'filled_checklist_preview_html': s.filled_checklist_preview_html,
        'report_checklist': s.report_checklist,
    }


# ── Chat ──────────────────────────────────────────────────────────────────

@app.post('/api/sessions/{sid}/chat')
async def chat(sid: str, req: ChatRequest):
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    s.messages.append({'role': 'user', 'content': req.message})
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
        response = f'Chat error: {e}'
    s.messages.append({'role': 'assistant', 'content': response})
    store.save(s)
    return {'success': True, 'response': response}
