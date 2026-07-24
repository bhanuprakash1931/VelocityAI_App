"""
RequirementsGenerator/backend/app/services.py
──────────────────────────────────────────────
Business logic for the Requirements Generator.
LLM calls are delegated to common.backend.llm_service.
"""
import json
import re
from datetime import datetime, timezone
from typing import Any

from common.backend.llm_service import llm_json as _llm_json
from .config import get_api_key, get_base_url, get_model
from .models import Column, RequirementTable, Version, Session

DEFAULT_COLUMNS = [
    "Req ID", "Category", "Requirement Statement", "Rationale / Source",
    "Acceptance Criteria", "Verification Method", "Owner", "Priority",
    "Status", "Comments",
]


# ---------------------------------------------------------------------------
# Convenience wrapper — injects this app's config callables
# ---------------------------------------------------------------------------

async def llm_json(system: str, user: str, timeout: int = 90) -> dict | None:
    return await _llm_json(
        system=system,
        user=user,
        get_api_key=get_api_key,
        get_base_url=get_base_url,
        get_model=get_model,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Demo / fallback helpers
# ---------------------------------------------------------------------------

def demo_analysis(needs: str) -> str:
    return (
        f"The requested system is analyzed from functional, performance, safety, "
        f"reliability, usability, interface, manufacturing, and verification perspectives. "
        f"Primary stakeholder intent: {needs.strip()}. "
        f"Ambiguous targets should be confirmed before release; every requirement "
        f"must be measurable, traceable, and independently verifiable."
    )


def clarifications(needs: str) -> list[str]:
    q: list[str] = []
    low = needs.lower()
    if not re.search(r"\d", needs):
        q.append("What measurable performance targets and tolerances should apply?")
    if not any(x in low for x in ["standard", "iec", "iso", "ul", "regulation"]):
        q.append("Which regulatory, safety, and industry standards apply?")
    if not any(x in low for x in ["environment", "temperature", "indoor", "outdoor"]):
        q.append("What operating and environmental conditions must be supported?")
    return q[:3]


def _is_dfmea(names: list[str]) -> bool:
    n = " ".join(re.sub(r"[^a-z0-9 ]+", "", c.lower()) for c in names)
    hits = sum(
        1 for kw in [
            "failure mode", "failure effect", "effects of failure",
            "severity", "occurrence", "detection", "rpn",
            "prevention", "cause", "mechanism",
        ]
        if kw in n
    )
    return hits >= 3


def demo_table(needs: str, columns: list[str] | None = None) -> RequirementTable:
    names = columns or DEFAULT_COLUMNS
    cols = [Column(name=x) for x in names]
    base = [
        ("REQ-001", "Functional", f"The system shall satisfy the stakeholder need: {needs.strip()[:80]}.",
         "Stakeholder need", "Demonstrated in an approved end-to-end scenario", "Test",
         "Systems", "High", "Draft", ""),
        ("REQ-002", "Performance", "The system shall complete each primary operation within 2 seconds.",
         "Derived performance target", "95th percentile response <= 2 s", "Test",
         "Software", "High", "Draft", "Confirm load profile"),
        ("REQ-003", "Reliability", "The system shall recover from a transient failure without loss of committed data.",
         "Reliability analysis", "Recovery succeeds and committed records remain intact", "Test",
         "Software", "High", "Draft", ""),
        ("REQ-004", "Security", "The system shall restrict protected operations to authenticated users.",
         "Security baseline", "All protected API tests reject unauthenticated access", "Inspection/Test",
         "Security", "Critical", "Draft", ""),
        ("REQ-005", "Usability", "The UI shall provide a visible outcome or error for every submitted operation.",
         "UX guideline", "100% of actions show success, progress, or actionable error", "Inspection",
         "UX", "Medium", "Draft", ""),
    ]
    canon = {n.lower(): i for i, n in enumerate(DEFAULT_COLUMNS)}
    rows = []
    for raw in base:
        rows.append([raw[canon[n.lower()]] if n.lower() in canon else "" for n in names])
    return RequirementTable(columns=cols, rows=rows)


def _col_role(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]+", "", name.lower()).strip()
    if any(x in n for x in ["req id", "requirement id", "serial", "id", "no"]):
        return "unique requirement ID e.g. REQ-001"
    if any(x in n for x in ["category", "type", "area", "section", "group"]):
        return "requirement category e.g. Functional / Performance / Safety"
    if any(x in n for x in ["description", "requirement statement", "shall statement", "requirement"]):
        return "measurable SHALL requirement statement"
    if any(x in n for x in ["source", "rationale", "origin", "reference"]):
        return "source or rationale e.g. Stakeholder need / Standard / Derived"
    if any(x in n for x in ["verification", "method", "test method"]):
        return "verification method: Inspection / Analysis / Test / Demonstration"
    if any(x in n for x in ["acceptance", "criteria", "target", "value"]):
        return "measurable acceptance criteria with units and limits"
    if any(x in n for x in ["owner", "responsibility", "responsible"]):
        return "responsible team or role e.g. Systems / Hardware / Software"
    if "priority" in n:
        return "priority: Critical / High / Medium / Low"
    if any(x in n for x in ["status", "result"]):
        return "status: Draft / Open / Verified / TBD"
    if any(x in n for x in ["comment", "remarks", "notes"]):
        return "reviewer notes or open questions"
    return f'value for column "{name}"'


# ---------------------------------------------------------------------------
# Core service functions
# ---------------------------------------------------------------------------

async def analyze(needs: str, context: str = ""):
    system = (
        "Return JSON only with keys analysis (string) and clarification_questions "
        "(array of strings). Analyze stakeholder needs for requirements engineering. "
        "Ask at most 3 essential questions."
    )
    result = await llm_json(system, needs + "\n" + "Additional context:\n" + context)
    if result is None:
        return (demo_analysis(needs), clarifications(needs))
    analysis = result.get("analysis") or ""
    questions = result.get("clarification_questions") or []
    if not isinstance(questions, list):
        questions = []
    return (analysis or demo_analysis(needs), questions)


async def generate(
    needs: str,
    analysis_text: str,
    columns: list[str] | None = None,
) -> RequirementTable:
    import logging
    _log = logging.getLogger("services")

    names = columns or DEFAULT_COLUMNS
    col_guidance = "\n".join(f'  col[{i}] "{n}" -> {_col_role(n)}' for i, n in enumerate(names))
    width = len(names)
    analysis_short = analysis_text[:2000] if analysis_text else ""
    needs_short = needs[:800] if needs else ""

    if _is_dfmea(names):
        system = (
            "You are a DFMEA engineer. Return ONLY valid JSON - no markdown, no prose.\n"
            'Shape: {"title": string, "rows": [[val0, val1, ...]]}\n'
            f"Rules: 12-16 rows. Each row = one failure mode. EXACTLY {width} elements per row.\n"
            "All cells non-empty. Severity/Occurrence/Detection = integer 1-10. RPN = S*O*D.\n"
            "Columns: " + ", ".join(f"[{i}]{n}" for i, n in enumerate(names))
        )
        user = json.dumps({"product": needs_short, "context": analysis_short})
    else:
        system = (
            "You are a requirements engineer. Return ONLY valid JSON - no markdown, no prose.\n"
            'Shape: {"title": string, "rows": [[val0, val1, ...]]}\n'
            f"Rules: 15-20 rows. EXACTLY {width} elements per row. No header row in rows.\n"
            "Write measurable SHALL statements with units.\n"
            "Column guidance:\n" + col_guidance
        )
        user = json.dumps({"stakeholder_needs": needs_short, "analysis": analysis_short, "columns": names})

    result = await llm_json(system, user, timeout=120)
    if not result:
        _log.warning("generate: llm_json returned None, using demo_table")
        return demo_table(needs, names)

    cols = [Column(name=n) for n in names]
    raw_rows = result.get("rows") or []
    if not isinstance(raw_rows, list) or not raw_rows:
        return demo_table(needs, names)

    rows = []
    for r in raw_rows:
        if not isinstance(r, (list, tuple)):
            continue
        padded = (list(r) + [""] * width)[:width]
        if [str(x).strip().lower() for x in padded] == [n.lower() for n in names]:
            continue
        if not any(str(x).strip() for x in padded):
            continue
        rows.append(padded)

    if not rows:
        return demo_table(needs, names)

    return RequirementTable(
        title=result.get("title", "Requirements Specification"),
        columns=cols,
        rows=rows,
    )


def add_version(s: Session, table: RequirementTable, source: str) -> Version:
    v = Version(
        version=f"v{len(s.versions) + 1}",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source=source,
        table=table,
        analysis=s.analysis,
        stakeholder_needs=s.stakeholder_needs,
    )
    s.versions.append(v)
    s.active_version = len(s.versions) - 1
    return v
