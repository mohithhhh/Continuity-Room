from typing import Literal

from pydantic import BaseModel, Field

FlagType = Literal["character", "prop", "location", "timeline"]
Severity = Literal["low", "medium", "high", "critical"]
ViewerRole = Literal["writers_room", "legal_standards", "marketing_safe"]


class StoryEvent(BaseModel):
    """One structured event extracted from a scene. Mirrors story_events."""

    episode: int
    scene: int
    character: str
    location: str
    time_of_day: str
    props_mentioned: list[str] = Field(default_factory=list)
    state_changes: list[str] = Field(default_factory=list)
    raw_excerpt: str


class ExtractionResult(BaseModel):
    """Structured output of the technical producer agent's Gemini call."""

    events: list[StoryEvent]


class ContinuityFlagDraft(BaseModel):
    """One contradiction as judged by the director agent, before it has been
    written to continuity_flags (event ids are ClickHouse UUID strings)."""

    event_id_a: str
    event_id_b: str
    flag_type: FlagType
    severity: Severity
    explanation: str


class ContinuityReport(BaseModel):
    """Structured output of the director agent's analysis pass."""

    script_id: str
    flags: list[ContinuityFlagDraft]
