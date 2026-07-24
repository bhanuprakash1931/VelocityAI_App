"""
RiskAssessor/backend/app/main.py
─────────────────────────────────
FastAPI application for the Risk Assessor.
Shared routes (config, health, sessions) are registered via common router factories.
"""
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path as FilePath
from uuid import uuid4

from .config import settings, get_api_key, get_base_url, get_model, set_runtime
from .models import (
    Session, AnalyzeRequest, GenerateRequest,
    TableRequest, ActionRequest, LlmConfigRequest,
    RiskTable,
)
from . import store
from .services import analyze, generate, generate_diagram_data, run_action, add_version

from common.backend.router import config_router, health_router, sessions_router
from common.backend.template_handler import save_upload, detect_template_columns
from common.backend.artifact_builder import export_xlsx_response

app = FastAPI(title='Velocity Risk Assessor API', version='1.0.0')

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
    session_factory=lambda: Session(id=str(uuid4()), title='New risk assessment session'),
))


# ── Upload ────────────────────────────────────────────────────────────────

@app.post('/api/sessions/{sid}/upload')
async def upload(sid: str, file: UploadFile = File(...)):
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    out, name = await save_upload(
        file=file,
        sid=sid,
        uploads_dir=settings.data_dir / 'uploads',
        max_upload_mb=settings.max_upload_mb,
    )
    s.files.append(str(out))
    store.save(s)
    columns = detect_template_columns(out) if out.suffix.lower() in {'.xlsx', '.xlsm'} else []
    return {'success': True, 'file': name, 'template_columns': columns}


# ── Analyze ───────────────────────────────────────────────────────────────

@app.post('/api/sessions/{sid}/analyze')
async def do_analyze(sid: str, req: AnalyzeRequest):
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    s.stakeholder_needs = req.stakeholder_needs.strip()
    s.title = s.stakeholder_needs[:60] or 'Risk assessment session'
    context_parts = [p for p in [req.additional_context, req.clarification_answers] if p and p.strip()]
    text, questions = await analyze(s.stakeholder_needs, '\n'.join(context_parts))
    s.analysis = text
    s.clarification_questions = questions
    s.messages += [
        {'role': 'user', 'content': req.stakeholder_needs},
        {'role': 'assistant', 'content': text},
    ]
    data: dict = {'analysis': text, 'clarification_questions': questions}
    if req.direct_generation:
        table = await generate(s.stakeholder_needs, s.analysis, req.template_columns)
        add_version(s, table, 'generated')
        data['table'] = table.model_dump()
    store.save(s)
    stage = 'clarification' if questions and not req.clarification_answers else 'analysis_complete'
    return {'success': True, 'stage': stage, 'data': data}


# ── Generate ──────────────────────────────────────────────────────────────

@app.post('/api/sessions/{sid}/generate')
async def do_generate(sid: str, req: GenerateRequest):
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    if not s.analysis:
        raise HTTPException(400, 'Run analysis first')
    table = await generate(s.stakeholder_needs, s.analysis, req.template_columns)
    v = add_version(s, table, 'generated')
    store.save(s)
    return {'success': True, 'stage': 'complete', 'data': {'table': table, 'version': v.version}}


# ── Save table ────────────────────────────────────────────────────────────

@app.put('/api/sessions/{sid}/table')
def save_table(sid: str, req: TableRequest):
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    table = RiskTable(columns=req.columns, rows=req.rows)
    v = add_version(s, table, req.source)
    store.save(s)
    return {'success': True, 'data': {'version': v.version}}


# ── Actions ───────────────────────────────────────────────────────────────

@app.post('/api/sessions/{sid}/actions/{action}')
async def action(sid: str, action: str, req: ActionRequest):
    if action not in {'query', 'review', 'update', 'revise'}:
        raise HTTPException(404, 'Unknown action')
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    table = s.versions[s.active_version].table if s.active_version >= 0 else None

    if action == 'revise' and table:
        rows = [list(r) for r in table.rows]
        ci = next(
            (i for i, c in enumerate(table.columns)
             if 'comment' in c.name.lower() or 'notes' in c.name.lower()),
            None,
        )
        if ci is not None:
            for r in rows:
                existing = str(r[ci]).strip(' |') if r[ci] else ''
                r[ci] = (existing + ' | Revision: ' + req.text).strip(' |') if existing else 'Revision: ' + req.text
        nv = RiskTable(title=table.title, columns=table.columns, rows=rows)
        v = add_version(s, nv, 'revised')
        store.save(s)
        return {'success': True, 'data': {'response': 'Revision captured in a new version.', 'table': nv, 'version': v.version}}

    if action == 'revise' and not table:
        raise HTTPException(400, 'Generate a risk register first')

    response = await run_action(action, req.text, table, s.analysis)
    s.messages.append({'role': 'assistant', 'content': response})
    store.save(s)
    return {'success': True, 'data': {'response': response}}


# ── Diagram / heatmap ─────────────────────────────────────────────────────

@app.get('/api/sessions/{sid}/diagram')
async def diagram(sid: str):
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    if s.active_version < 0:
        raise HTTPException(400, 'Generate a risk register first')
    t = s.versions[s.active_version].table
    data = await generate_diagram_data(t)
    return {'success': True, 'data': data}


# ── Export XLSX ───────────────────────────────────────────────────────────

@app.get('/api/sessions/{sid}/export.xlsx')
def export_xlsx(sid: str):
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    if s.active_version < 0:
        raise HTTPException(400, 'Generate a risk register first')
    t = s.versions[s.active_version].table
    return export_xlsx_response(
        columns=[c.name for c in t.columns],
        rows=t.rows,
        sheet_title='Risk Register',
        filename='risk_register.xlsx',
    )
