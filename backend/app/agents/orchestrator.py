"""Explicit three-agent pipeline graph.

Each stage below is a fully separate ADK agent (see producer.py, director.py,
studio_head.py), each constructed with its own distinct, restricted tool
bindings enforced at construction time — not a single agent with access to
everything. This module IS the graph: it decides which agent runs when and
what data flows between them, as explicit Python control flow rather than
wrapping the three in a single ADK `SequentialAgent`. That's a deliberate
choice, not a shortcut: the technical producer's and studio head's
ClickHouse writes are deterministic Python triggered after each agent's
structured output validates (see those modules' docstrings for why —
letting an LLM's tool-call reconstruct write payloads risks silent
transcription errors in exactly the rows an audit trail depends on).
"""

from pydantic import BaseModel, Field

from app.agents.director import run_director
from app.agents.producer import run_technical_producer
from app.agents.studio_head import run_studio_head
from app.schemas import ContinuityReport


class PipelineStageResult(BaseModel):
    stage: str
    status: str
    detail: str = ""


class PipelineResult(BaseModel):
    script_id: str
    stages: list[PipelineStageResult] = Field(default_factory=list)
    events_written: int = 0
    report: ContinuityReport | None = None
    studio_head_summary: str = ""


async def run_pipeline(script_id: str, raw_text: str) -> PipelineResult:
    """Runs technical producer -> director -> studio head in sequence
    against one script excerpt, returning per-stage status for the
    frontend's status view."""
    result = PipelineResult(script_id=script_id)

    try:
        written = await run_technical_producer(script_id, raw_text)
        result.events_written = len(written)
        result.stages.append(
            PipelineStageResult(
                stage="technical_producer",
                status="complete",
                detail=f"{len(written)} event(s) extracted and written to story_events",
            )
        )
    except Exception as exc:
        result.stages.append(
            PipelineStageResult(stage="technical_producer", status="failed", detail=str(exc))
        )
        raise

    try:
        report = await run_director(script_id)
        result.report = report
        result.stages.append(
            PipelineStageResult(
                stage="director",
                status="complete",
                detail=f"{len(report.flags)} continuity issue(s) identified",
            )
        )
    except Exception as exc:
        result.stages.append(
            PipelineStageResult(stage="director", status="failed", detail=str(exc))
        )
        raise

    try:
        summary = await run_studio_head(report)
        result.studio_head_summary = summary
        result.stages.append(
            PipelineStageResult(stage="studio_head", status="complete", detail=summary)
        )
    except Exception as exc:
        result.stages.append(
            PipelineStageResult(stage="studio_head", status="failed", detail=str(exc))
        )
        raise

    return result
