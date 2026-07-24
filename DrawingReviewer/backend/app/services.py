"""
DrawingReviewer/backend/app/services.py
────────────────────────────────────────
Business logic for the Drawing Reviewer.
LLM calls are delegated to common.backend.llm_service.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from common.backend.llm_service import llm_json as _llm_json, llm_vision_json as _llm_vision_json
from .config import get_api_key, get_base_url, get_model

_log = logging.getLogger('drawing_reviewer.services')

# ── Resolve VelocityAI_Platform path ──────────────────────────────────────
APP_DIR          = Path(__file__).resolve().parent
BACKEND_DIR      = APP_DIR.parent
DRAWING_DIR      = BACKEND_DIR.parent
VELOCITY_APP_DIR = DRAWING_DIR.parent
ROOT_DIR         = VELOCITY_APP_DIR.parent
DESKTOP_DIR      = ROOT_DIR.parent


def _find_platform() -> Path:
    candidates = [
        ROOT_DIR / "VelocityAI_Platform",
        DESKTOP_DIR / "VELOCITY_AI" / "VelocityAI_Platform",
        ROOT_DIR.parent / "VELOCITY_AI" / "VelocityAI_Platform",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


PLATFORM_DIR = _find_platform()
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))


# ---------------------------------------------------------------------------
# Convenience wrappers — inject this app's config callables
# ---------------------------------------------------------------------------

async def llm_json(system: str, user: str, timeout: int = 120) -> dict | None:
    return await _llm_json(
        system=system, user=user,
        get_api_key=get_api_key, get_base_url=get_base_url, get_model=get_model,
        timeout=timeout,
    )


async def llm_vision_json(prompt: str, images_b64: list[dict], timeout: int = 180) -> dict | None:
    return await _llm_vision_json(
        prompt=prompt, images_b64=images_b64,
        get_api_key=get_api_key, get_base_url=get_base_url, get_model=get_model,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# PDF → images
# ---------------------------------------------------------------------------

def _pdf_to_images(pdf_path: str, max_pages: int = 20) -> list[dict]:
    """Convert PDF pages to base64 images."""
    images: list[dict] = []
    try:
        from pdf2image import convert_from_path  # type: ignore
        pages = convert_from_path(pdf_path, dpi=150, first_page=1, last_page=max_pages)
        for i, page in enumerate(pages, 1):
            import io
            buf = io.BytesIO()
            page.save(buf, format='JPEG', quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode()
            images.append({'page': i, 'b64': b64, 'mime_type': 'image/jpeg'})
        _log.info('pdf2image: converted %d pages from %s', len(images), pdf_path)
        return images
    except ImportError:
        _log.info('pdf2image not available, trying pypdf fallback')
    except Exception as e:
        _log.warning('pdf2image failed: %s', e)

    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        for i, page in enumerate(reader.pages[:max_pages], 1):
            for img_obj in page.images:
                try:
                    b64 = base64.b64encode(img_obj.data).decode()
                    images.append({'page': i, 'b64': b64, 'mime_type': 'image/jpeg'})
                    break
                except Exception:
                    pass
        _log.info('pypdf fallback: extracted %d images from %s', len(images), pdf_path)
    except Exception as e:
        _log.warning('pypdf fallback failed: %s', e)

    return images


# ---------------------------------------------------------------------------
# Demo / fallback payloads
# ---------------------------------------------------------------------------

def _demo_extracted() -> dict:
    return {
        'title_block': {
            'drawing_number': 'DEMO-DWG-001',
            'title': 'Demo Engineering Drawing',
            'revision': 'A',
            'material': 'Not extracted (demo mode)',
            'scale': '1:1',
            'units': 'mm',
        },
        'revision_block': [{'rev': 'A', 'description': 'Initial release', 'date': 'TBD'}],
        'views': ['Front view', 'Section A-A'],
        'dimensions': [{'value': '100', 'unit': 'mm'}, {'value': '50', 'unit': 'mm'}],
        'tolerances': ['±0.1 mm general'],
        'annotations': [],
        'gdt': [],
        'general_notes': ['All dimensions in mm unless otherwise stated.'],
        'missing_fields': ['Vision analysis unavailable — no API key or vision model not configured.'],
        'uncertain_fields': [],
        'analysis_error': 'Demo mode — configure an OpenAI-compatible API key and a vision model to enable real drawing analysis.',
    }


def _demo_check(extracted: dict) -> dict:
    return {
        'overall_score': 0,
        'summary': 'Demo mode — configure API key for real analysis.',
        'findings': [
            {'id': 'F1', 'severity': 'info', 'category': 'General',
             'text': 'Drawing analysis is running in demo mode. No API key is configured.',
             'recommendation': 'Configure an OpenAI-compatible API key via the settings panel.',
             'checked': False},
        ],
    }


def _demo_report_sections(check: dict) -> dict:
    return {
        'summary': 'Drawing review completed in demo mode. Configure an API key for AI-powered analysis.',
        'key_findings': ['Demo mode active — real findings require a configured LLM.'],
        'recommendations': ['Configure an API key via the settings panel and re-run the review.'],
        'engineering_review_notes': ['AI-generated findings are review assistance only and do not replace engineering approval.'],
    }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """You are reviewing engineering drawing pages. Extract all visible structured data.
Return ONLY valid JSON with these keys:
{
  "title_block": {},
  "revision_block": [],
  "views": [],
  "dimensions": [],
  "tolerances": [],
  "annotations": [],
  "gdt": [],
  "general_notes": [],
  "missing_fields": [],
  "uncertain_fields": []
}
Rules:
- If a field is unreadable, use "Unknown" and add to uncertain_fields.
- Do NOT invent drawing numbers, dimensions, tolerances, material, revision, signatures, or units.
- Preserve exact visible text where possible."""

CHECK_PROMPT = """Check the extracted drawing data against the best practices below.
Return ONLY valid JSON:
{
  "overall_score": 0,
  "summary": "",
  "findings": [
    {"id": "F1", "text": "", "severity": "warning", "category": "", "recommendation": "", "checked": false}
  ]
}
Severity: info | warning | error | critical. Do not create fake findings."""

REPORT_PROMPT = """Create a concise engineering drawing review report summary.
Return ONLY valid JSON with keys: summary, key_findings, recommendations, engineering_review_notes.
Do NOT return Markdown tables, headings, or blank bullet items.
Each value is a string (for summary) or array of strings (for the rest).
State clearly that AI findings are review assistance and do not replace engineering approval."""


# ---------------------------------------------------------------------------
# Core service functions
# ---------------------------------------------------------------------------

async def run_analyze(drawing_paths: list[str], best_practices: str) -> dict[str, Any]:
    """Extract drawing data and run best-practice check."""
    all_images: list[dict] = []
    for path in drawing_paths:
        all_images.extend(_pdf_to_images(path, max_pages=20))
    page_count = len(all_images)
    _log.info('run_analyze: %d pages from %d PDFs', page_count, len(drawing_paths))

    extracted: dict[str, Any] = {}
    if all_images:
        result = await llm_vision_json(EXTRACTION_PROMPT, all_images[:20], timeout=180)
        if result:
            extracted = result
        else:
            _log.warning('run_analyze: vision extraction returned None, using demo')
            extracted = _demo_extracted()
    else:
        _log.warning('run_analyze: no images extracted, using demo')
        extracted = _demo_extracted()

    if not isinstance(extracted.get('title_block'), dict):
        extracted['title_block'] = {}
    for key in ('revision_block', 'views', 'dimensions', 'tolerances', 'annotations',
                'gdt', 'general_notes', 'missing_fields', 'uncertain_fields'):
        if not isinstance(extracted.get(key), list):
            extracted[key] = []

    bp = best_practices.strip() if best_practices else _default_best_practices()
    check_user = json.dumps({'best_practices': bp[:4000], 'extracted_data': extracted}, ensure_ascii=False)[:16000]
    check_result = await llm_json(CHECK_PROMPT, check_user, timeout=120)
    if not check_result:
        _log.warning('run_analyze: check returned None, using demo check')
        check_result = _demo_check(extracted)
    if not isinstance(check_result.get('findings'), list):
        check_result['findings'] = []

    return {
        'page_count': page_count,
        'extracted_data': extracted,
        'check_results': check_result,
    }


async def run_report(
    drawing_paths: list[str],
    extracted_data: dict[str, Any],
    check_results: dict[str, Any],
    template_path: str | None,
    best_practices: str,
) -> dict[str, Any]:
    """Generate Word/PDF report and filled checklist."""
    report_user = json.dumps({
        'extracted_data': extracted_data,
        'check_results': check_results,
    }, ensure_ascii=False)[:16000]
    sections = await llm_json(REPORT_PROMPT, report_user, timeout=120)
    if not sections:
        _log.warning('run_report: report LLM returned None, using demo sections')
        sections = _demo_report_sections(check_results)

    for key in ('key_findings', 'recommendations', 'engineering_review_notes'):
        if isinstance(sections.get(key), str):
            sections[key] = [l.strip(' -*•') for l in sections[key].splitlines() if l.strip(' -*•')]
        elif not isinstance(sections.get(key), list):
            sections[key] = []

    checklist = []
    for i, f in enumerate(check_results.get('findings', []), 1):
        if not isinstance(f, dict):
            continue
        text = str(f.get('text') or f.get('description') or '').strip()
        if not text:
            continue
        checklist.append({
            'id': f.get('id') or f'F{i}',
            'severity': str(f.get('severity') or 'info').lower(),
            'category': str(f.get('category') or 'General'),
            'text': text,
            'recommendation': str(f.get('recommendation') or ''),
            'checked': bool(f.get('checked', False)),
        })

    preview_html = ''
    docx_path = ''
    pdf_path = ''
    filled_path = ''
    filled_preview = ''
    try:
        from .report_builder import (
            build_normalized_report, build_report_preview_html,
            build_drawing_review_docx, build_drawing_review_pdf,
        )
        normalized = build_normalized_report(
            extracted_data=extracted_data, check_results=check_results,
            checklist=checklist, report_sections=sections,
            drawing_files=drawing_paths,
        )
        preview_html = build_report_preview_html(normalized)
        docx_path = build_drawing_review_docx(
            extracted_data=extracted_data, check_results=check_results,
            checklist=checklist, report_sections=sections,
            drawing_files=drawing_paths,
        )
        pdf_path = build_drawing_review_pdf(
            extracted_data=extracted_data, check_results=check_results,
            checklist=checklist, report_sections=sections,
            drawing_files=drawing_paths,
        )
    except Exception as e:
        _log.exception('run_report: artifact generation failed: %s', e)
        preview_html = _fallback_preview_html(extracted_data, check_results, sections)

    if template_path and Path(template_path).exists():
        try:
            from .excel_checklist_writer import (
                fill_uploaded_checklist_copy_fast, build_filled_checklist_preview_html,
            )
            filled_path = fill_uploaded_checklist_copy_fast(
                template_path=template_path, checklist=checklist,
                extracted_data=extracted_data, check_results=check_results,
                report_docx_path=docx_path,
            )
            filled_preview = build_filled_checklist_preview_html(filled_path)
        except Exception as e:
            _log.exception('run_report: checklist fill failed: %s', e)

    return {
        'report_sections': sections,
        'report_checklist': checklist,
        'report_preview_html': preview_html,
        'report_docx_path': docx_path,
        'report_pdf_path': pdf_path,
        'filled_checklist_path': filled_path,
        'filled_checklist_preview_html': filled_preview,
    }


async def run_chat(
    message: str,
    extracted_data: dict[str, Any],
    check_results: dict[str, Any],
    report_sections: dict[str, Any],
    report_checklist: list[dict[str, Any]],
    chat_history: str,
) -> str:
    """Ground Q&A in the drawing analysis context."""
    if not extracted_data:
        return (
            'No drawing analysis is available yet. '
            'Upload a drawing PDF and click Analyze Drawing first.'
        )
    from common.backend.llm_service import llm_chat_completion
    system = (
        'You are an expert mechanical design engineer and engineering drawing reviewer. '
        'Answer questions grounded only in the extracted drawing data, check results, '
        'report sections, and checklist provided. '
        'Mark uncertainty explicitly. Never invent unreadable values. '
        'If the answer is not present, say that manual engineering review is required.'
    )
    user = (
        f'# User question\n{message}\n\n'
        f'# Extracted data\n{json.dumps(extracted_data, ensure_ascii=False)[:8000]}\n\n'
        f'# Check results\n{json.dumps(check_results, ensure_ascii=False)[:6000]}\n\n'
        f'# Report sections\n{json.dumps(report_sections, ensure_ascii=False)[:4000]}\n\n'
        f'# Checklist findings\n{json.dumps(report_checklist, ensure_ascii=False)[:3000]}'
    )
    return await llm_chat_completion(
        system=system, user=user,
        get_api_key=get_api_key, get_base_url=get_base_url, get_model=get_model,
        timeout=60, max_tokens=1024,
        no_key_message='Chat requires an API key. Configure one via the settings panel.',
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_best_practices() -> str:
    bp_path = PLATFORM_DIR / 'apps' / 'drawing_reviewer' / 'config' / 'default_best_practices.md'
    if bp_path.exists():
        return bp_path.read_text(encoding='utf-8')
    return (
        'Engineering Drawing Best Practices:\n'
        '- Title Block: include drawing number, revision, material, scale, units, dates, drawn-by.\n'
        '- Revision Block: each revision shall include ID, description, date, and initials.\n'
        '- Views: front view should be present; sections/details/auxiliaries should be labelled.\n'
        '- Dimensions: functional dimensions should be present once with units.\n'
        '- Tolerances: critical dimensions should include tolerances or a general tolerance note.\n'
        '- GD&T: feature control frames should reference valid datums.\n'
        '- Release readiness: safety-critical findings require human review before release.'
    )


def _fallback_preview_html(extracted: dict, checks: dict, sections: dict) -> str:
    import html
    summary = str(sections.get('summary', 'Drawing review completed.'))
    findings_rows = ''.join(
        f'<tr><td>{html.escape(str(f.get('id'', '')))}'
        f'</td><td><b>{html.escape(str(f.get('severity'', '')))}'
        f'</b></td><td>{html.escape(str(f.get('category'', '')))}'
        f'</td><td>{html.escape(str(f.get('text'', '')))}'
        f'</td><td>{html.escape(str(f.get('recommendation'', '')))}'
        f'</td></tr>'
        for f in checks.get('findings'', [])[:50]
    )
    return (
        '<div style="font-family:Inter,Arial,sans-serif;font-size:13px;padding:14px;">'
        '<h1>Drawing Review Report</h1>'
        f'<h2>Review Summary</h2><p>{html.escape(summary)}</p>'
        '<h2>Key Findings</h2>'
        '<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:100%;">'
        '<thead><tr style="background:#1F4E78;color:white;">'
        '<th>ID</th><th>Severity</th><th>Category</th><th>Finding</th><th>Recommendation</th>'
        '</tr></thead>'
        f'<tbody>{findings_rows}</tbody></table>'
        '<p><b>Human engineering review required before release or manufacturing use.</b></p>'
        '</div>'
    )
