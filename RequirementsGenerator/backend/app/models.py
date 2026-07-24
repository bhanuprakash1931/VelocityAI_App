"""
RequirementsGenerator/backend/app/models.py
────────────────────────────────────────────
App-specific Pydantic models.
Shared base models (Column, LlmConfigRequest, ApiResult, BaseSession)
are imported from common.backend.models.
"""
from typing import Any
from pydantic import Field
from common.backend.models import Column, LlmConfigRequest, ApiResult, BaseSession  # noqa: F401


class RequirementTable(BaseSession.__class__.__bases__[0]):
    """A generated requirements or DFMEA table."""
    title: str = "Requirements Specification"
    columns: list[Column]
    rows: list[list[Any]]

    class Config:
        arbitrary_types_allowed = True


from pydantic import BaseModel


class RequirementTable(BaseModel):
    title: str = "Requirements Specification"
    columns: list[Column]
    rows: list[list[Any]]


class Version(BaseModel):
    version: str
    timestamp: str
    source: str
    table: RequirementTable
    analysis: str = ""
    stakeholder_needs: str = ""


class Session(BaseSession):
    title: str = "Untitled session"
    stakeholder_needs: str = ""
    analysis: str = ""
    clarification_questions: list[str] = Field(default_factory=list)
    versions: list[Version] = Field(default_factory=list)
    active_version: int = -1


class AnalyzeRequest(BaseModel):
    stakeholder_needs: str
    additional_context: str = ""
    clarification_answers: str = ""
    direct_generation: bool = False
    template_columns: list[str] | None = None


class GenerateRequest(BaseModel):
    template_columns: list[str] | None = None


class TableRequest(BaseModel):
    columns: list[Column]
    rows: list[list[Any]]
    source: str = "user_edit"


class ActionRequest(BaseModel):
    text: str
