"""Director agent — analysis.

Privilege boundary: this agent's ONLY path to ClickHouse is the official
read-only ClickHouse MCP server (`mcp-clickhouse`, launched as a subprocess),
restricted at the ADK tool-binding level (`tool_filter`) to
list_databases / list_tables / run_query. No clickhouse-connect import
exists anywhere in this module or its dependents — there is no code path by
which this agent could write to the store, not just a documented
convention. The MCP server subprocess itself is also launched with
CLICKHOUSE_ALLOW_WRITE_ACCESS hardcoded to "false" (not read from settings),
so even a compromised or misconfigured tool_filter can't turn run_query into
a write.
"""

import sys
import uuid

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

from app.agents.runtime import run_agent_once
from app.config import settings
from app.schemas import ContinuityReport

CANDIDATE_CHARACTER_QUERY = """
SELECT
    a.event_id AS event_id_a, b.event_id AS event_id_b,
    a.character AS character, a.episode AS episode_a, a.scene AS scene_a,
    a.state_changes AS state_changes_a, a.raw_excerpt AS raw_excerpt_a,
    b.episode AS episode_b, b.scene AS scene_b,
    b.state_changes AS state_changes_b, b.raw_excerpt AS raw_excerpt_b
FROM continuity_room.story_events AS a
INNER JOIN continuity_room.story_events AS b
    -- case-insensitive: extraction isn't guaranteed to capitalize a
    -- character's name the same way in every scene (e.g. "MARA" vs "Mara")
    ON lower(a.character) = lower(b.character) AND a.script_id = b.script_id
WHERE a.script_id = '<SCRIPT_ID>' AND (a.episode, a.scene) < (b.episode, b.scene)
ORDER BY a.character, a.episode, a.scene
""".strip()

CANDIDATE_PROP_QUERY = """
SELECT
    x.event_id AS event_id_a, y.event_id AS event_id_b, x.prop AS shared_prop,
    x.episode AS episode_a, x.scene AS scene_a, x.raw_excerpt AS raw_excerpt_a,
    y.episode AS episode_b, y.scene AS scene_b, y.raw_excerpt AS raw_excerpt_b
FROM
(
    SELECT event_id, script_id, episode, scene, raw_excerpt, arrayJoin(props) AS prop
    FROM continuity_room.story_events WHERE script_id = '<SCRIPT_ID>'
) AS x
INNER JOIN
(
    SELECT event_id, script_id, episode, scene, raw_excerpt, arrayJoin(props) AS prop
    FROM continuity_room.story_events WHERE script_id = '<SCRIPT_ID>'
) AS y
ON lower(x.prop) = lower(y.prop) AND x.script_id = y.script_id
WHERE (x.episode, x.scene) < (y.episode, y.scene)
ORDER BY x.prop, x.episode, x.scene
""".strip()

FULL_TIMELINE_QUERY = (
    "SELECT event_id, episode, scene, character, location, time_of_day, "
    "props, state_changes, raw_excerpt FROM continuity_room.story_events "
    "WHERE script_id = '<SCRIPT_ID>' ORDER BY episode, scene"
)

INSTRUCTION = f"""You are the director on a TV writers' room continuity team.
You have read-only tools onto a ClickHouse store: list_databases, list_tables,
and run_query. You have no write tools — you cannot modify anything.

The user message tells you which script_id to analyze. Follow this exact plan:

1. Call list_tables once against database "continuity_room" to confirm the
   schema you're working with.

2. Call run_query with this exact SQL, substituting the real script_id for
   <SCRIPT_ID>, to load the full ordered event timeline for the script:
   {FULL_TIMELINE_QUERY}

3. Call run_query with this exact SQL (substituting <SCRIPT_ID>) to surface
   candidate character-state contradictions — pairs of events for the same
   character across different scenes:
   {CANDIDATE_CHARACTER_QUERY}

4. Call run_query with this exact SQL (substituting <SCRIPT_ID>) to surface
   candidate prop contradictions — pairs of events sharing a prop across
   different scenes:
   {CANDIDATE_PROP_QUERY}

5. Using the results of steps 2-4, identify real contradictions:
   - character: a character's physical state (injury, ability, wardrobe)
     changes between scenes with no in-story explanation (healing, time
     skip, off-screen event) — check the candidate pairs from step 3.
   - prop: an object described as destroyed, lost, or given away reappears
     later in the same or a contradictory state — check the candidate pairs
     from step 4.
   - location / timeline: contradictory conditions (weather, time elapsed,
     established facts) between scenes that the script presents as
     continuous or nearby in time — find these by reading the full ordered
     timeline from step 2 yourself; they will not be caught by steps 3-4.
   Only treat a change as explained by time passing if the script gives an
   EXPLICIT signal of it (e.g. a stated time skip, dialogue referencing
   elapsed time, a visible healing process). The mere fact that two events
   are in different episodes or scenes is NOT by itself such a signal — an
   injury that is bandaged and painful in one scene and fully, silently
   gone with no mention in the very next scene the character appears in is
   a contradiction, not an assumed offscreen recovery. When in doubt
   between flagging and not flagging, flag it at a lower severity rather
   than silently dropping it.

6. Rank every real contradiction you find by severity:
   - critical: breaks the core plot logic of the episode
   - high: a clearly visible, avoidable continuity error a viewer would spot
   - medium: a minor inconsistency an attentive viewer might notice
   - low: a trivial or arguable inconsistency

7. Return a structured report: for each contradiction, the two event_ids
   involved (event_id_a, event_id_b, using the real UUIDs from the query
   results — never invent an id), its flag_type (character/prop/location/
   timeline), its severity, and a one-to-two sentence explanation citing the
   specific detail that conflicts."""

director_agent = LlmAgent(
    name="director",
    model=settings.gemini_model,
    instruction=INSTRUCTION,
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    # mcp-clickhouse is a direct pip dependency (see
                    # requirements.txt) of this same environment, so we
                    # launch it via the running interpreter rather than
                    # depending on `uvx`/`uv` being present on the host —
                    # this is what actually runs in the Cloud Run container.
                    command=sys.executable,
                    args=["-c", "from mcp_clickhouse.main import main; main()"],
                    env={
                        "CLICKHOUSE_HOST": settings.clickhouse_host,
                        "CLICKHOUSE_PORT": str(settings.clickhouse_port),
                        "CLICKHOUSE_USER": settings.clickhouse_user,
                        "CLICKHOUSE_PASSWORD": settings.clickhouse_password,
                        "CLICKHOUSE_DATABASE": settings.clickhouse_database,
                        "CLICKHOUSE_SECURE": (
                            "true" if settings.clickhouse_secure else "false"
                        ),
                        # Hardcoded — never sourced from settings — so this
                        # agent's MCP server can never be write-enabled by a
                        # config mistake elsewhere.
                        "CLICKHOUSE_ALLOW_WRITE_ACCESS": "false",
                    },
                ),
            ),
            tool_filter=["list_databases", "list_tables", "run_query"],
        )
    ],
    output_schema=ContinuityReport,
    output_key="continuity_report",
)


async def run_director(script_id: str) -> ContinuityReport:
    raw_json = await run_agent_once(
        director_agent,
        f"Analyze script_id = '{script_id}' for continuity contradictions.",
        app_name="continuity_room_director",
        session_id=f"director-{script_id}-{uuid.uuid4().hex[:8]}",
    )
    return ContinuityReport.model_validate_json(raw_json)
