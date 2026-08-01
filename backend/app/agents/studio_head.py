"""Studio head agent — governance.

Privilege boundary: this is the ONLY module in the codebase that writes to
continuity_flags or audit_log. `actor_agent` on every audit row is hardcoded
here, never taken from an LLM- or caller-supplied argument, so nothing can
forge an audit entry's identity. Role-scoped reads go through the ClickHouse
views defined in db/ddl.sql (vw_writers_room / vw_legal_standards /
vw_marketing_safe) — the RBAC boundary between audiences is enforced in SQL,
not by the application filtering rows after the fact.
"""

import uuid

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from app.agents.runtime import run_agent_once
from app.clickhouse.client import get_client
from app.config import settings
from app.schemas import ContinuityReport, ViewerRole

_VIEW_BY_ROLE: dict[str, str] = {
    "writers_room": "vw_writers_room",
    "legal_standards": "vw_legal_standards",
    "marketing_safe": "vw_marketing_safe",
}


def _record_audit_log(
    *, actor_agent: str, action: str, target: str, viewer_role: str, details: str = ""
) -> None:
    client = get_client()
    client.insert(
        "audit_log",
        [[str(uuid.uuid4()), actor_agent, action, target, viewer_role, details]],
        column_names=[
            "id",
            "actor_agent",
            "action",
            "target",
            "viewer_role",
            "details",
        ],
    )


def _persist_flags(report: ContinuityReport) -> dict:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    if not report.flags:
        return {"flags_written": 0, **counts}

    client = get_client()
    rows = []
    for flag in report.flags:
        rows.append(
            [
                str(uuid.uuid4()),
                report.script_id,
                flag.event_id_a,
                flag.event_id_b,
                flag.flag_type,
                flag.severity,
                flag.explanation,
                "open",
            ]
        )
        counts[flag.severity] += 1

    client.insert(
        "continuity_flags",
        rows,
        column_names=[
            "id",
            "script_id",
            "event_id_a",
            "event_id_b",
            "flag_type",
            "severity",
            "explanation",
            "status",
        ],
    )
    return {"flags_written": len(rows), **counts}


def persist_report(report_json: str) -> dict:
    """Persist the director agent's continuity report to continuity_flags
    and record the corresponding audit log entry. `report_json` must be the
    director's report passed through verbatim, unmodified.

    Args:
        report_json: the exact JSON text of the director's ContinuityReport.

    Returns:
        A dict with script_id, flags_written, and counts by severity.
    """
    report = ContinuityReport.model_validate_json(report_json)
    result = _persist_flags(report)
    _record_audit_log(
        actor_agent="studio_head",
        action="report_generated",
        target=report.script_id,
        viewer_role="system",
        details=(
            f"{result['flags_written']} flags written "
            f"(critical={result['critical']}, high={result['high']}, "
            f"medium={result['medium']}, low={result['low']})"
        ),
    )
    return {"script_id": report.script_id, **result}


INSTRUCTION = """You are the studio head on a TV writers' room continuity team.
You will receive the director's continuity report as JSON in the user
message. Call the persist_report tool exactly once, passing the report JSON
through EXACTLY as you received it as the report_json argument — do not
reformat, re-type, summarize, or alter any field. Then report back the
script_id, how many flags were written, and the counts by severity from the
tool's return value."""

studio_head_agent = LlmAgent(
    name="studio_head",
    model=settings.gemini_model,
    instruction=INSTRUCTION,
    tools=[FunctionTool(persist_report)],
)


async def run_studio_head(report: ContinuityReport) -> str:
    """Runs the studio head agent on a director report, returning its final
    confirmation text. The actual write happens deterministically inside the
    persist_report tool, not by trusting the LLM to reconstruct row data."""
    return await run_agent_once(
        studio_head_agent,
        report.model_dump_json(),
        app_name="continuity_room_studio_head",
        session_id=f"studio-head-{report.script_id}-{uuid.uuid4().hex[:8]}",
    )


def get_role_scoped_view(script_id: str, role: ViewerRole) -> list[dict]:
    """Deterministic RBAC read path used by the API layer (independent of
    the agent pipeline run) — any time a viewer of a given role looks at a
    script's flags, this is the sole function that serves that read, and it
    always logs the access."""
    view_name = _VIEW_BY_ROLE[role]
    client = get_client()
    result = client.query(
        f"SELECT * FROM {view_name} WHERE script_id = {{script_id:String}}",
        parameters={"script_id": script_id},
    )
    rows = [dict(zip(result.column_names, row)) for row in result.result_rows]
    _record_audit_log(
        actor_agent="studio_head",
        action="view_accessed",
        target=script_id,
        viewer_role=role,
        details=f"{len(rows)} rows returned",
    )
    return rows
