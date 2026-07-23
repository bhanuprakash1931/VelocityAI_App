from pydantic import BaseModel, Field
from typing import Any, Optional
from uuid import uuid4
from datetime import datetime


class LlmConfigRequest(BaseModel):
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = "Drawing Review Session"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
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
    messages: list[dict[str, str]] = []


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