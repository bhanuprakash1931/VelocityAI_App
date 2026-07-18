import json
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import settings, get_api_key, get_base_url, get_model
from .models import Column, RiskTable, Version, Session

DEFAULT_RISK_COLUMNS = [
    "Risk ID", "Category", "Risk Statement", "Cause", "Event", "Impact",
    "Affected Asset/Process", "Existing Controls", "Control Effectiveness",
    "Likelihood", "Impact Rating", "Overall Rating", "Proposed Mitigation",
    "Contingency Plan", "Owner", "Due Date", "Residual Risk", "Status",
    "Evidence / Source", "Confidence", "Notes",
]

RISK_CATEGORIES = [
    "Strategic", "Operational", "Financial", "Compliance/Legal", "Safety",
    "Security", "Privacy", "Technology", "Supplier/Third-party", "Schedule",
    "Quality", "Environmental", "Reputational", "People/Resource",
    "Change/Adoption",
]


# ---------------------------------------------------------------------------
# Low-level LLM helpers
# ---------------------------------------------------------------------------

def _json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    a = text.find("{")
    b = text.rfind("}")
    return json.loads(text[a : b + 1])


async def llm_json(system: str, user: str, timeout: int = 120) -> dict | None:
    api_key = get_api_key()
    if not api_key:
        return None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": get_model(),
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(
                get_base_url().rstrip("/") + "/chat/completions",
                headers=headers,
                json=payload,
            )
            r.raise_for_status()
            return _json(r.json()["choices"][0]["message"]["content"])
    except httpx.ConnectError:
        return None
    except httpx.TimeoutException:
        import logging
        logging.getLogger("services").warning("llm_json timed out after %ds", timeout)
        return None
    except httpx.HTTPStatusError as e:
        import logging
        logging.getLogger("services").warning(
            "OpenAI HTTP error %s: %s", e.response.status_code, e.response.text[:200]
        )
        return None
    except Exception:
        import logging
        logging.getLogger("services").exception("llm_json unexpected error")
        return None


# ---------------------------------------------------------------------------
# Demo / fallback helpers
# ---------------------------------------------------------------------------

def _is_dfmea(names: list[str]) -> bool:
    n = " ".join(re.sub(r"[^a-z0-9 ]+", "", c.lower()) for c in names)
    hits = sum(
        1
        for kw in [
            "failure mode", "failure effect", "effects of failure",
            "severity", "occurrence", "detection", "rpn",
            "prevention", "cause", "mechanism",
        ]
        if kw in n
    )
    return hits >= 3


def demo_analysis(needs: str) -> str:
    return (
        f"Risk analysis for: {needs.strip()}.\n\n"
        "**Summary**: The described context has been assessed for strategic, operational, "
        "financial, compliance, safety, security, technology, supplier, schedule, quality, "
        "and reputational risk exposure.\n\n"
        "**Key Risk Themes**:\n"
        "- Unclear performance targets and thresholds create measurement risk.\n"
        "- Missing regulatory, safety, and standards context creates compliance risk.\n"
        "- Undefined operating environment creates operational and reliability risk.\n"
        "- Unspecified owner/accountability creates governance risk.\n\n"
        "**Note**: Provide measurable targets, applicable standards, operating conditions, "
        "and risk appetite to improve the quality of this assessment."
    )


def demo_clarifications(needs: str) -> list[str]:
    q: list[str] = []
    low = needs.lower()
    if not re.search(r"\d", needs):
        q.append("What measurable performance targets, thresholds, and tolerances should apply?")
    if not any(x in low for x in ["standard", "iec", "iso", "ul", "regulation", "compliance"]):
        q.append("Which regulatory, safety, and industry standards or frameworks apply?")
    if not any(x in low for x in ["environment", "temperature", "indoor", "outdoor", "condition"]):
        q.append("What operating and environmental conditions must be supported?")
    if not any(x in low for x in ["owner", "team", "responsible", "stakeholder"]):
        q.append("Who are the risk owners and accountable stakeholders?")
    return q[:3]


def demo_risk_table(needs: str, columns: list[str] | None = None) -> RiskTable:
    names = columns or DEFAULT_RISK_COLUMNS
    cols = [Column(name=x) for x in names]
    product = needs.strip()[:60]

    if _is_dfmea(names):
        dfmea_base = [
            ("Battery pack", "Battery pack shall prevent thermal runaway",
             "Cell overcharge / BMS failure", "Fire, injury, product recall",
             "9", "Safety Critical", "BMS IC failure; welded FET", "3",
             "Dual-threshold BMS protection; firmware validation", "EOL charge cycle test",
             "3", "81", "Add independent hardware cutoff; increase BMS coverage",
             "Electrical/Safety", "TBD", "Open"),
            ("Motor assembly", "Motor shall maintain rated output under nominal load",
             "Motor stall due to blockage", "Loss of performance; overheating; shutdown",
             "7", "Performance Critical", "Debris bypass inlet; filter saturation", "4",
             "Inlet mesh 4mm; thermal cutoff", "Stall detection; EOL test",
             "4", "112", "Reduce inlet aperture; add thermal cutoff",
             "Mechanical/Software", "TBD", "Open"),
            ("Filter assembly", "Filter shall trap ≥99% of particles ≥0.3µm",
             "Filter bypass / seal failure", "Dust emission; user exposure; non-compliance",
             "7", "Regulatory", "Incorrect installation; seal deformation", "3",
             "Keyed housing; seal torque spec", "Filtration efficiency test",
             "3", "63", "Redesign filter latch; add installation indicator",
             "Systems/Manufacturing", "TBD", "Open"),
            ("Housing", "Housing shall withstand 1m drop without cracking",
             "Housing crack on drop", "Loss of structural integrity; user injury",
             "6", "Reliability", "Wall thickness insufficient; material brittleness", "3",
             "FEA drop simulation; material review", "1m drop test on all faces",
             "3", "54", "Increase wall thickness; add rib structure",
             "Mechanical", "TBD", "Open"),
        ]
        dfmea_cols = [
            "Item / Component", "Function / Risk Assessment", "Potential Failure Mode",
            "Potential Effects of Failure", "Severity (S)", "Classification",
            "Potential Causes / Mechanisms", "Occurrence (O)", "Prevention Controls",
            "Detection Controls", "Detection (D)", "RPN", "Recommended Actions",
            "Owner", "Target Date", "Action Status",
        ]
        d_canon = {n.lower(): i for i, n in enumerate(dfmea_cols)}
        rows = []
        for raw in dfmea_base:
            row = [raw[d_canon[n.lower()]] if n.lower() in d_canon else "TBD" for n in names]
            rows.append(row)
        return RiskTable(title=f"DFMEA / Risk Register — {product}", columns=cols, rows=rows)

    # Standard risk register demo rows
    base_risks = [
        ("R-001", "Strategic",
         "Because of unclear objectives, scope creep may occur, resulting in project overrun.",
         "Unclear objectives", "Scope creep", "Project overrun and cost increase",
         "Project delivery", "Scope baseline document", "Partial",
         "Medium", "High", "High",
         "Define and freeze scope baseline; implement change control",
         "Descope non-critical features", "Project Manager", "TBD",
         "Medium", "Open", "Stakeholder input", "Medium", "Review at kick-off"),
        ("R-002", "Operational",
         "Because of inadequate testing coverage, defects may reach production, resulting in service disruption.",
         "Inadequate QA", "Defects in production", "Service disruption and rework costs",
         "Software delivery", "Code review process", "Partial",
         "Medium", "High", "High",
         "Increase automated test coverage to ≥80%; add regression suite",
         "Rollback plan", "QA Lead", "TBD",
         "Medium", "Open", "QA metrics", "Medium", ""),
        ("R-003", "Compliance/Legal",
         "Because of missing regulatory mapping, non-compliance may occur, resulting in fines or market withdrawal.",
         "No regulatory review", "Non-compliance finding", "Fines, withdrawal, reputational damage",
         "Product / Legal", "Informal compliance checks", "Low",
         "Low", "Critical", "High",
         "Engage compliance SME; map applicable regulations; conduct gap analysis",
         "Emergency legal review", "Legal / Compliance", "TBD",
         "Medium", "Open", "Regulatory framework", "Low", ""),
        ("R-004", "Safety",
         "Because of insufficient hazard analysis, a safety event may occur, resulting in user injury.",
         "No formal HAZOP", "Safety event", "User injury; liability; recall",
         "Hardware design", "Design review", "Partial",
         "Low", "Critical", "High",
         "Conduct HAZOP/FMEA; apply IEC 62368 or relevant standard",
         "Product recall procedure", "Safety Engineer", "TBD",
         "Low", "Open", "HAZOP report", "Low", ""),
        ("R-005", "Technology",
         "Because of third-party API dependency, an outage may occur, resulting in service unavailability.",
         "Single supplier dependency", "API outage", "Service unavailability",
         "Integration / API", "SLA monitoring", "Partial",
         "Medium", "Medium", "Medium",
         "Add fallback provider; implement circuit breaker pattern",
         "Manual workaround procedure", "Architect", "TBD",
         "Low", "Open", "SLA contract", "Medium", ""),
        ("R-006", "Security",
         "Because of unpatched dependencies, a breach may occur, resulting in data loss and reputational damage.",
         "Dependency management gap", "Security breach", "Data loss; regulatory fine; reputation",
         "Software / Infrastructure", "Periodic manual review", "Low",
         "Medium", "High", "High",
         "Automate dependency scanning (SAST/SCA); enforce patch SLA",
         "Incident response plan", "Security Lead", "TBD",
         "Medium", "Open", "Security scan reports", "Medium", ""),
        ("R-007", "Schedule",
         "Because of resource unavailability, milestone delays may occur, resulting in missed delivery commitments.",
         "Resource constraints", "Milestone delay", "Missed commitments; customer dissatisfaction",
         "Project management", "Resource plan", "Partial",
         "Medium", "Medium", "Medium",
         "Identify and onboard backup resources; buffer critical path",
         "Re-plan with reduced scope", "Programme Manager", "TBD",
         "Low", "Open", "Resource plan", "Medium", ""),
        ("R-008", "Financial",
         "Because of cost estimation gaps, budget overrun may occur, resulting in reduced programme funding.",
         "Estimation uncertainty", "Budget overrun", "Reduced funding; programme impact",
         "Finance / PMO", "Budget reviews", "Partial",
         "Low", "High", "Medium",
         "Add 15% contingency reserve; monthly cost tracking",
         "Descope or request supplemental budget", "CFO / PMO", "TBD",
         "Low", "Open", "Cost model", "Low", ""),
    ]
    canon = {n.lower(): i for i, n in enumerate(DEFAULT_RISK_COLUMNS)}
    rows = []
    for raw in base_risks:
        rows.append([raw[canon[n.lower()]] if n.lower() in canon else "" for n in names])
    return RiskTable(columns=cols, rows=rows)


# ---------------------------------------------------------------------------
# Column role guidance for LLM prompts
# ---------------------------------------------------------------------------

def _col_role(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]+", "", name.lower()).strip()
    if any(x in n for x in ["risk id", "id", "serial", "s no", "sno", "no"]):
        return "unique risk ID e.g. R-001"
    if any(x in n for x in ["category", "type", "area"]):
        return "risk category e.g. Strategic / Operational / Financial / Compliance / Safety / Security / Technology"
    if any(x in n for x in ["risk statement", "statement", "description", "risk"]):
        return "cause-event-impact risk statement: 'Because of [cause], [event] may occur, resulting in [impact]'"
    if any(x in n for x in ["cause", "root cause"]):
        return "root cause or trigger of the risk"
    if n == "event" or "risk event" in n:
        return "risk event that may occur"
    if any(x in n for x in ["impact", "consequence", "effect"]):
        return "consequence or impact if the risk materialises"
    if any(x in n for x in ["affected asset", "asset", "process"]):
        return "affected asset, process, or system"
    if any(x in n for x in ["existing control", "current control", "control"]):
        return "existing controls already in place"
    if "control effectiveness" in n:
        return "effectiveness of existing controls: Strong / Partial / Weak / None"
    if any(x in n for x in ["likelihood", "probability"]):
        return "likelihood: Low / Medium / High / TBD"
    if "impact rating" in n or "severity" in n:
        return "impact rating: Low / Medium / High / Critical / TBD"
    if any(x in n for x in ["overall rating", "risk rating", "score"]):
        return "overall risk rating: Low / Medium / High / Critical / TBD"
    if any(x in n for x in ["proposed mitigation", "mitigation", "treatment"]):
        return "proposed mitigation or risk treatment action"
    if any(x in n for x in ["contingency", "fallback"]):
        return "contingency plan if risk materialises"
    if any(x in n for x in ["owner", "risk owner", "assigned"]):
        return "risk owner: team or role name"
    if any(x in n for x in ["due date", "target date"]):
        return "target date for mitigation: YYYY-MM-DD or TBD"
    if "residual risk" in n:
        return "residual risk after mitigation: Low / Medium / High / TBD"
    if any(x in n for x in ["status", "state"]):
        return "status: Open / In Progress / Closed / TBD"
    if any(x in n for x in ["evidence", "source", "reference"]):
        return "evidence source or reference document"
    if "confidence" in n:
        return "confidence in rating: High / Medium / Low"
    if any(x in n for x in ["notes", "comment", "remark"]):
        return "additional notes or reviewer comments"
    # DFMEA columns
    if any(x in n for x in ["item", "component"]):
        return "system item or component name"
    if "failure mode" in n:
        return "potential failure mode description"
    if "effects of failure" in n or "failure effect" in n:
        return "potential effect of failure on system/user"
    if n in {"severity", "severity s", "s"}:
        return "severity rating 1-10"
    if "classification" in n or "special characteristic" in n:
        return "safety/special characteristic classification"
    if "cause" in n or "mechanism" in n:
        return "potential cause or mechanism of failure"
    if n in {"occurrence", "occurrence o", "o"}:
        return "occurrence rating 1-10"
    if "prevention" in n:
        return "current prevention control"
    if "detection control" in n:
        return "current detection control"
    if n in {"detection", "detection d", "d"}:
        return "detection rating 1-10"
    if n == "rpn":
        return "Risk Priority Number = Severity × Occurrence × Detection"
    if "recommended action" in n:
        return "recommended corrective action"
    if "target date" in n or "due date" in n:
        return "target completion date"
    if "action result" in n or "actions taken" in n:
        return "result of action taken"
    return f'value for column "{name}"'


# ---------------------------------------------------------------------------
# Core service functions
# ---------------------------------------------------------------------------

async def analyze(needs: str, context: str = "") -> tuple[str, list[str]]:
    system = (
        "You are a senior risk analyst. Return JSON only with keys: "
        "\"analysis\" (string — structured risk analysis with sections: Summary, "
        "Key Risk Themes, Facts and Assumptions, Existing Controls, Gaps and Ambiguities) "
        "and \"clarification_questions\" (array of strings — at most 3 essential questions "
        "needed before a quality risk register can be produced). "
        "Use cause-event-impact wording. Do not invent facts, ratings, owners, dates, "
        "regulations, or SLAs. Use TBD for missing values."
    )
    user = (
        f"Stakeholder context:\n{needs}\n\n"
        f"Additional context:\n{context}"
    )
    result = await llm_json(system, user)
    if result is None:
        return (demo_analysis(needs), demo_clarifications(needs))
    analysis = result.get("analysis") or ""
    questions = result.get("clarification_questions") or []
    if not isinstance(questions, list):
        questions = []
    return (analysis or demo_analysis(needs), questions)


async def generate(
    needs: str,
    analysis_text: str,
    columns: list[str] | None = None,
) -> RiskTable:
    import logging
    _log = logging.getLogger("services")

    names = columns or DEFAULT_RISK_COLUMNS
    width = len(names)
    col_guidance = "\n".join(
        f"  col[{i}] \"{n}\" -> {_col_role(n)}" for i, n in enumerate(names)
    )
    analysis_short = analysis_text[:3000] if analysis_text else ""
    needs_short = needs[:1000] if needs else ""

    if _is_dfmea(names):
        system = (
            "You are a DFMEA engineer. Return ONLY valid JSON — no markdown, no prose.\n"
            "Shape: {\"title\": string, \"rows\": [[val0, val1, ...]]}\n"
            f"Rules: 12-16 rows. Each row = one failure mode. EXACTLY {width} elements per row.\n"
            "All cells non-empty. Severity/Occurrence/Detection = integer 1-10. RPN = S×O×D.\n"
            "Subsystems: battery, motor, filtration, housing, charger, UI, seal, structure.\n"
            "Owner = engineering role. Do NOT repeat column names as values.\n"
            "Columns: " + ", ".join(f"[{i}]{n}" for i, n in enumerate(names))
        )
        user = json.dumps({"product": needs_short, "context": analysis_short})
    else:
        system = (
            "You are a senior risk analyst. Return ONLY valid JSON — no markdown, no prose.\n"
            "Shape: {\"title\": string, \"rows\": [[val0, val1, ...]]}\n"
            f"Rules: 12-20 rows. EXACTLY {width} elements per row. No header row in rows.\n"
            "Use cause-event-impact wording for Risk Statement.\n"
            "Likelihood / Impact Rating / Overall Rating = Low / Medium / High / Critical / TBD.\n"
            "Control Effectiveness = Strong / Partial / Weak / None.\n"
            "Status = Open (default). Do not invent owners, dates, regulations, SLAs.\n"
            "Cover: Strategic, Operational, Financial, Compliance, Safety, Security, "
            "Technology, Supplier, Schedule, Quality, Environmental, Reputational.\n"
            "Column guidance:\n" + col_guidance
        )
        user = json.dumps({
            "stakeholder_needs": needs_short,
            "analysis": analysis_short,
            "columns": names,
        })

    result = await llm_json(system, user, timeout=120)
    if not result:
        _log.warning(
            "generate: llm_json returned None, using demo_risk_table (is_dfmea=%s, cols=%d)",
            _is_dfmea(names), width,
        )
        return demo_risk_table(needs, names)

    cols = [Column(name=n) for n in names]
    raw_rows = result.get("rows") or []
    _log.info("generate: llm returned %d rows for %d columns", len(raw_rows), width)

    if not isinstance(raw_rows, list) or not raw_rows:
        _log.warning("generate: no valid rows in LLM response, using demo_risk_table")
        return demo_risk_table(needs, names)

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
        _log.warning("generate: all rows empty after filtering, using demo_risk_table")
        return demo_risk_table(needs, names)

    _log.info("generate: returning %d rows with %d columns", len(rows), width)
    return RiskTable(
        title=result.get("title", "Risk Register"),
        columns=cols,
        rows=rows,
    )


async def generate_diagram_data(table: RiskTable) -> dict:
    """Build risk matrix / heatmap data from the risk table."""
    rows = table.rows
    columns = [c.name for c in table.columns]

    def _idx(*candidates: str) -> int | None:
        norm = [re.sub(r"[^a-z0-9 ]+", "", c.lower()).strip() for c in columns]
        for cand in candidates:
            n = re.sub(r"[^a-z0-9 ]+", "", cand.lower()).strip()
            for i, col in enumerate(norm):
                if n == col or n in col:
                    return i
        return None

    id_idx = _idx("risk id", "id", "serial")
    cat_idx = _idx("category", "type")
    stmt_idx = _idx("risk statement", "statement", "description")
    like_idx = _idx("likelihood", "probability")
    impact_idx = _idx("impact rating", "impact", "severity")
    overall_idx = _idx("overall rating", "risk rating", "score")
    owner_idx = _idx("owner", "risk owner")
    status_idx = _idx("status")

    def _cell(row: list, idx: int | None, default: str = "TBD") -> str:
        if idx is None or idx >= len(row):
            return default
        v = row[idx]
        return default if v is None else str(v).strip() or default

    def _rating_level(val: str) -> int:
        v = val.lower()
        if "critical" in v:
            return 4
        if "high" in v:
            return 3
        if "medium" in v or "moderate" in v:
            return 2
        if "low" in v:
            return 1
        return 0

    risks = []
    category_counts: dict[str, int] = {}

    for row in rows:
        rid = _cell(row, id_idx, "R-?")
        cat = _cell(row, cat_idx, "Uncategorised")
        stmt = _cell(row, stmt_idx, "Risk statement TBD")[:120]
        likelihood = _cell(row, like_idx, "TBD")
        impact = _cell(row, impact_idx, "TBD")
        overall = _cell(row, overall_idx, "TBD")
        owner = _cell(row, owner_idx, "TBD")
        status = _cell(row, status_idx, "Open")

        category_counts[cat] = category_counts.get(cat, 0) + 1
        risks.append({
            "id": rid,
            "category": cat,
            "statement": stmt,
            "likelihood": likelihood,
            "impact": impact,
            "overall": overall,
            "likelihood_level": _rating_level(likelihood),
            "impact_level": _rating_level(impact),
            "overall_level": _rating_level(overall),
            "owner": owner,
            "status": status,
        })

    # Build heatmap grid (5×5: likelihood vs impact)
    heatmap: list[dict] = []
    labels = ["", "Low", "Medium", "High", "Critical"]
    for l_level in range(1, 5):
        for i_level in range(1, 5):
            cell_risks = [
                r["id"]
                for r in risks
                if r["likelihood_level"] == l_level and r["impact_level"] == i_level
            ]
            heatmap.append({
                "likelihood_level": l_level,
                "likelihood_label": labels[l_level],
                "impact_level": i_level,
                "impact_label": labels[i_level],
                "risk_ids": cell_risks,
                "count": len(cell_risks),
            })

    # Build mermaid flowchart
    lines = ["flowchart LR", "A[Stakeholder Context] --> B[Risk Analysis]", "B --> C[Risk Register]"]
    for cat, count in list(category_counts.items())[:8]:
        safe_cat = re.sub(r"[^a-zA-Z0-9]", "_", cat)
        lines.append(f'C --> {safe_cat}["{cat} — {count} risk(s)"]')
        cat_risks = [r for r in risks if r["category"] == cat][:3]
        for r in cat_risks:
            safe_id = re.sub(r"[^a-zA-Z0-9]", "_", r["id"])
            label = r["id"] + " " + r["overall"]
            lines.append(f'{safe_cat} --> {safe_id}["{label}"]')

    return {
        "risks": risks,
        "heatmap": heatmap,
        "category_counts": category_counts,
        "mermaid": "\n".join(lines),
        "total": len(risks),
        "high_critical": sum(1 for r in risks if r["overall_level"] >= 3),
    }


async def run_action(
    action: str,
    text: str,
    table: RiskTable | None,
    analysis: str = "",
) -> str:
    """Handle query / review / update / revise actions."""
    row_count = len(table.rows) if table else 0
    table_summary = ""
    if table and table.rows:
        col_names = [c.name for c in table.columns]
        table_summary = "\n".join(
            " | ".join(f"{col_names[j]}: {cell}" for j, cell in enumerate(row[:6]))
            for row in table.rows[:15]
        )

    if action == "query":
        system = (
            "You are a senior risk analyst. Answer the user's question using only "
            "the provided risk context. Be concise and actionable. "
            "If context is insufficient, state what is missing."
        )
        user = (
            f"USER QUESTION\n{text}\n\n"
            f"RISK ANALYSIS\n{analysis[:2000]}\n\n"
            f"RISK REGISTER SAMPLE (first 15 rows)\n{table_summary}"
        )

    elif action == "review":
        system = (
            "You are a risk assessment reviewer. Review the given risk item for: "
            "clarity, specificity, cause-event-impact completeness, measurability, "
            "control adequacy, and mitigation quality. Provide: "
            "(1) Issues (bullets), (2) Improved rewrite, (3) Recommended action."
        )
        user = f"RISK ITEM TO REVIEW\n{text}\n\nCONTEXT\n{analysis[:1500]}"

    elif action == "update":
        system = (
            "You are a risk analyst. Apply the user's update instruction to the risk register. "
            "Return: (A) Interpretation, (B) Proposed change(s), (C) Impact on other risks."
        )
        user = (
            f"UPDATE INSTRUCTION\n{text}\n\n"
            f"CURRENT RISK REGISTER SAMPLE\n{table_summary}\n\n"
            f"ANALYSIS CONTEXT\n{analysis[:1500]}"
        )

    else:
        # revise / generic
        return (
            f"Revision noted: '{text}'. "
            + (f"The current risk register contains {row_count} risks. " if table else "")
            + "Review likelihood ratings, impact ratings, controls, and mitigation quality "
            "against the updated context before re-approving."
        )

    result = await llm_json(system, user)
    if result is None:
        # Fallback plain-text response
        return (
            f"{action.title()} assessment for: '{text}'. "
            + (f"The risk register contains {row_count} risks. " if table else "")
            + "Evaluate cause-event-impact completeness, control adequacy, "
            "mitigation specificity, owner assignment, and residual risk before approval."
        )

    # LLM may return structured JSON or a plain string; flatten to text
    if isinstance(result, dict):
        parts = []
        for k, v in result.items():
            if isinstance(v, list):
                parts.append(f"**{k}**\n" + "\n".join(f"- {item}" for item in v))
            else:
                parts.append(f"**{k}**\n{v}")
        return "\n\n".join(parts)
    return str(result)


def add_version(s: Session, table: RiskTable, source: str) -> Version:
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