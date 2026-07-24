"""
RequirementsGenerator/backend/app/main.py
──────────────────────────────────────────
FastAPI application for the Requirements Generator.
Shared routes (config, health, sessions) are registered via common router factories.
"""
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pathlib import Path as FilePath
from uuid import uuid4
from io import BytesIO

from .config import settings, get_api_key, get_base_url, get_model, set_runtime
from .models import (
    Session, AnalyzeRequest, GenerateRequest,
    TableRequest, ActionRequest, LlmConfigRequest,
    RequirementTable, Column,
)
from . import store
from .services import analyze, generate, add_version

from common.backend.router import config_router, health_router, sessions_router
from common.backend.template_handler import save_upload, detect_template_columns
from common.backend.artifact_builder import export_xlsx_response

app = FastAPI(title='Velocity Requirements API', version='2.0.0')

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
    session_factory=lambda: Session(id=str(uuid4()), title='New requirements session'),
))


# ── Upload ────────────────────────────────────────────────────────────────

@app.post('/api/sessions/{sid}/upload')
async def upload(sid: str, file: UploadFile = File(...)):
    s = store.load(sid) if sid else None
    if s is None:
        raise HTTPException(404, 'Session not found')
    out, name = await save_upload(
        file=file,
        sid=sid,
        uploads_dir=settings.data_dir / 'uploads',
        max_upload_mb=settings.max_upload_mb,
    )
    s.files.append(str(out))
    store.save(s)
    columns = detect_template_columns(out) if out.suffix.lower() in {'xlsx', '.xlsm'} else []
    # Also try .xlsx without leading dot
    if not columns and out.suffix.lower() in {'.xlsx', '.xlsm'}:
        columns = detect_template_columns(out)
    return {'success': True, 'file': name, 'template_columns': columns}


# ── Analyze ───────────────────────────────────────────────────────────────

@app.post('/api/sessions/{sid}/analyze')
async def do_analyze(sid: str, req: AnalyzeRequest):
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    s.stakeholder_needs = req.stakeholder_needs.strip()
    s.title = s.stakeholder_needs[:60] or 'Requirements session'
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
    table = RequirementTable(columns=req.columns, rows=req.rows)
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
        ci = next((i for i, c in enumerate(table.columns) if 'comment' in c.name.lower()), None)
        if ci is not None:
            for r in rows:
                existing = str(r[ci]).strip(' |') if r[ci] else ''
                r[ci] = (existing + ' | Revision: ' + req.text).strip(' |') if existing else 'Revision: ' + req.text
        nv = RequirementTable(title=table.title, columns=table.columns, rows=rows)
        v = add_version(s, nv, 'revised')
        store.save(s)
        return {'success': True, 'data': {'response': 'Revision captured in a new version.', 'table': nv, 'version': v.version}}

    if action == 'revise' and not table:
        raise HTTPException(400, 'Generate requirements first')

    row_count = len(table.rows) if table else 0
    response = (
        f'{action.title()} assessment: {req.text}. '
        + (f'The current table contains {row_count} requirements. ' if table else ''
        ) + 'Review traceability, measurability, feasibility, and verification impact before approval.'
    )
    s.messages.append({'role': 'assistant', 'content': response})
    store.save(s)
    return {'success': True, 'data': {'response': response}}


# ── Diagram ───────────────────────────────────────────────────────────────

@app.get('/api/sessions/{sid}/diagram')
def diagram(sid: str):
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    if s.active_version < 0:
        raise HTTPException(400, 'Generate requirements first')
    t = s.versions[s.active_version].table
    lines = ['flowchart LR', 'A[Stakeholder Needs] --> B[Analysis]', 'B --> C[Requirements]']
    for i, row in enumerate(t.rows[:10]):
        lines.append(f'C --> R{i}[{str(row[0] if row else i + 1).replace("[", "(").replace("]", ")")}]')
    return {'success': True, 'data': {'mermaid': '\n'.join(lines)}}


# ── Export XLSX ───────────────────────────────────────────────────────────

@app.get('/api/sessions/{sid}/export.xlsx')
def export_xlsx(sid: str):
    try:
        s = store.load(sid)
    except FileNotFoundError:
        raise HTTPException(404, 'Session not found')
    if s.active_version < 0:
        raise HTTPException(400, 'Generate requirements first')
    t = s.versions[s.active_version].table
    return export_xlsx_response(
        columns=[c.name for c in t.columns],
        rows=t.rows,
        sheet_title='Requirements',
        filename='requirements.xlsx',
    )
