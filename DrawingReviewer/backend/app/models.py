"""
DrawingReviewer/backend/app/models.py
──────────────────────────────────────
App-specific Pydantic models.
Shared base models (Column, LlmConfigRequest, ApiResult, BaseSession)
are imported from common.backend.models.
"""
from typing import Any, Optional
from pydantic import BaseModel, Field
from common.backend.models import LlmConfigRequest, ApiResult, BaseSession  # noqa: F401


class Session(BaseSession):
    title: str = "Drawing Review Session"
    drawing_paths: list[str] = []
    template_path: Optional[str] = None
    analysis_done: bool = False
    report_done: bool = False
    extracted_data: dict[str, Any] = {}
    check_results: dict[str, Any] = {}
    report_sections: dict[str, Any] = {}
    report_checklist: list[dict[str, Any]] = []
    report_preview_html: str = ""
    report_docx_path: str = ""
    report_pdf_path: str = ""
    filled_checklist_path: str = ""
    filled_checklist_preview_html: str = ""


class AnalyzeRequest(BaseModel):
    drawing_paths: list[str] = []
    best_practices: str = ""


class ReportRequest(BaseModel):
    drawing_paths: list[str] = []
    template_path: Optional[str] = None
    best_practices: str = ""


class ChatRequest(BaseModel):
    message: str
    chat_history: str = ""
