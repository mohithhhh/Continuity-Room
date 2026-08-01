"""Technical producer agent — ingestion.

Privilege boundary: this is the ONLY module in the codebase that writes to
story_events, and it writes nothing else. It has no read/query access to
ClickHouse beyond the write it just performed (no client method here ever
issues a SELECT).
"""

import uuid

from google.adk.agents import LlmAgent

from app.agents.runtime import run_agent_once
from app.clickhouse.client import get_client
from app.config import settings
from app.schemas import ExtractionResult, StoryEvent

INSTRUCTION = """You are the technical producer on a TV writers' room continuity team.

Given a raw script excerpt (one or more scenes, possibly spanning multiple
episodes), extract one structured event per (character, scene) combination
that appears in the text. For each event capture:

- episode: the episode number stated or clearly implied by the text (integer)
- scene: the scene number stated or clearly implied by the text (integer)
- character: the character's name exactly as written in the script
- location: the scene's location/setting (from the slugline)
- time_of_day: DAY, NIGHT, MORNING, EVENING, or as stated in the slugline
- props_mentioned: notable physical objects this character interacts with or
  that are described in this scene (e.g. "silver pocket watch", "bandage")
- state_changes: notable physical, wardrobe, or relational state changes for
  this character in this scene (injuries, healing, clothing, relationship
  shifts), as short phrases — omit if nothing changed
- raw_excerpt: the exact lines of action/dialogue from the source text that
  support this event, verbatim, trimmed to the relevant lines

Extract every character with a speaking or acting presence in a scene as a
separate event. Do not invent details that aren't present in the text.
Return only the structured events."""

technical_producer_agent = LlmAgent(
    name="technical_producer",
    model=settings.gemini_model,
    instruction=INSTRUCTION,
    output_schema=ExtractionResult,
    output_key="extraction",
)


def _write_events(
    script_id: str, events: list[StoryEvent]
) -> list[tuple[str, StoryEvent]]:
    """The only write path into story_events. Deliberately deterministic
    Python rather than an LLM-invoked tool call: a malformed extraction can
    fail schema validation upstream, but it can never cause the wrong SQL to
    run, because there's only ever this one INSERT shape.
    """
    if not events:
        return []

    client = get_client()
    rows = []
    written: list[tuple[str, StoryEvent]] = []
    for event in events:
        event_id = str(uuid.uuid4())
        rows.append(
            [
                event_id,
                script_id,
                event.episode,
                event.scene,
                event.character,
                event.location,
                event.time_of_day,
                event.props_mentioned,
                event.state_changes,
                event.raw_excerpt,
            ]
        )
        written.append((event_id, event))

    client.insert(
        "story_events",
        rows,
        column_names=[
            "event_id",
            "script_id",
            "episode",
            "scene",
            "character",
            "location",
            "time_of_day",
            "props",
            "state_changes",
            "raw_excerpt",
        ],
    )
    return written


async def run_technical_producer(
    script_id: str, raw_text: str
) -> list[tuple[str, StoryEvent]]:
    """Extracts structured events from raw script text via Gemini, then
    writes them to ClickHouse. Returns (event_id, StoryEvent) pairs for the
    rows just written."""
    raw_json = await run_agent_once(
        technical_producer_agent,
        raw_text,
        app_name="continuity_room_producer",
        session_id=f"producer-{script_id}-{uuid.uuid4().hex[:8]}",
    )
    result = ExtractionResult.model_validate_json(raw_json)
    return _write_events(script_id, result.events)
