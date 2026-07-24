"""
common/backend/models.py
──────────────────────────
Shared Pydantic models used by all Velocity AI applications.

Import in each app's models.py:

    from common.backend.models import (
        Column,
        LlmConfigRequest,
        ApiResult,
        BaseSession,
    )
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4
from datetime import datetime, timezone

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Column descriptor — used in table-based apps (RequirementsGenerator,
# RiskAssessor) to describe each column of a generated table.
# ---------------------------------------------------------------------------

class Column(BaseModel):
    """Describes a single column in a generated data table."""

    name: str
    data_type: str = "string"
    editable: bool = True


# ---------------------------------------------------------------------------
# LLM configuration request — identical payload shape across all apps.
# ---------------------------------------------------------------------------

class LlmConfigRequest(BaseModel):
    """PUT /api/config request body."""

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"


# ---------------------------------------------------------------------------
# Generic API result envelope.
# ---------------------------------------------------------------------------

class ApiResult(BaseModel):
    """Standard JSON envelope returned by action endpoints."""

    success: bool = True
    stage: str = "complete"
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


# ---------------------------------------------------------------------------
# Base session — every app's Session model extends this.
# ---------------------------------------------------------------------------

class BaseSession(BaseModel):
    """
    Common session fields shared by all Velocity AI applications.

    App-specific sessions should extend this class and add their own fields:

        from common.backend.models import BaseSession

        class Session(BaseSession):
            stakeholder_needs: str = ""
            analysis: str = ""
            versions: list[Version] = Field(default_factory=list)
            active_version: int = -1
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = "Untitled session"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    files: list[str] = Field(default_factory=list)
    messages: list[dict[str, str]] = Field(default_factory=list)
