-- Continuity Room — ClickHouse schema
--
-- Privilege model enforced by who is allowed to touch which of these:
--   - story_events    : written ONLY by the technical producer agent
--                        (backend/app/agents/producer.py, clickhouse-connect)
--   - continuity_flags: written ONLY by the studio head agent, from the
--                        director agent's report (backend/app/agents/studio_head.py)
--   - audit_log       : written ONLY by the studio head agent
--   - vw_*            : read-only views the studio head agent selects from
--                        to apply role-based access before handing a report
--                        to a given audience
-- The director agent never writes; it only ever runs `run_query` /
-- `list_tables` / `list_databases` through the read-only ClickHouse MCP
-- server (CLICKHOUSE_ALLOW_WRITE_ACCESS=false), against story_events and
-- continuity_flags.

CREATE DATABASE IF NOT EXISTS continuity_room;

-- ---------------------------------------------------------------------------
-- story_events: one row per structured event extracted from a scene.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS continuity_room.story_events
(
    event_id        UUID DEFAULT generateUUIDv4(),
    script_id       String,
    episode         UInt16,
    scene           UInt16,
    character       String,
    location        String,
    time_of_day     LowCardinality(String),
    props           Array(String),
    state_changes   Array(String),
    raw_excerpt     String,
    ingested_at     DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
ORDER BY (script_id, episode, scene, character);

-- ---------------------------------------------------------------------------
-- continuity_flags: one row per contradiction the director agent surfaces
-- and the studio head agent has approved for publication to Grafana.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS continuity_room.continuity_flags
(
    id              UUID DEFAULT generateUUIDv4(),
    script_id       String,
    event_id_a      UUID,
    event_id_b      UUID,
    flag_type       Enum8('character' = 1, 'prop' = 2, 'location' = 3, 'timeline' = 4),
    severity        Enum8('low' = 1, 'medium' = 2, 'high' = 3, 'critical' = 4),
    explanation     String,
    status          Enum8('open' = 1, 'resolved' = 2, 'dismissed' = 3) DEFAULT 'open',
    created_at      DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
ORDER BY (severity, created_at);

-- ---------------------------------------------------------------------------
-- audit_log: one row per report generated and per role-scoped view accessed.
-- Written only by the studio head agent.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS continuity_room.audit_log
(
    id              UUID DEFAULT generateUUIDv4(),
    actor_agent     LowCardinality(String),
    action          LowCardinality(String),
    target          String,
    viewer_role     LowCardinality(String),
    details         String DEFAULT '',
    timestamp       DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
ORDER BY (timestamp);

-- ---------------------------------------------------------------------------
-- Role-based views over continuity_flags + story_events, applied by the
-- studio head agent depending on the requesting audience.
-- ---------------------------------------------------------------------------

-- Writers' room: full detail, both conflicting excerpts, no redaction.
CREATE VIEW IF NOT EXISTS continuity_room.vw_writers_room AS
SELECT
    f.id                AS flag_id,
    f.script_id         AS script_id,
    f.flag_type         AS flag_type,
    f.severity          AS severity,
    f.explanation        AS explanation,
    f.status            AS status,
    f.created_at        AS created_at,
    a.episode           AS episode_a,
    a.scene             AS scene_a,
    a.character         AS character_a,
    a.raw_excerpt        AS raw_excerpt_a,
    b.episode           AS episode_b,
    b.scene             AS scene_b,
    b.character         AS character_b,
    b.raw_excerpt        AS raw_excerpt_b
FROM continuity_room.continuity_flags AS f
LEFT JOIN continuity_room.story_events AS a ON a.event_id = f.event_id_a
LEFT JOIN continuity_room.story_events AS b ON b.event_id = f.event_id_b;

-- Legal / standards: risk-flagged only (severity >= high), no raw excerpts.
CREATE VIEW IF NOT EXISTS continuity_room.vw_legal_standards AS
SELECT
    f.id                AS flag_id,
    f.script_id         AS script_id,
    f.flag_type         AS flag_type,
    f.severity          AS severity,
    f.explanation        AS explanation,
    f.status            AS status,
    f.created_at        AS created_at,
    a.episode           AS episode_a,
    a.scene             AS scene_a,
    b.episode           AS episode_b,
    b.scene             AS scene_b
FROM continuity_room.continuity_flags AS f
LEFT JOIN continuity_room.story_events AS a ON a.event_id = f.event_id_a
LEFT JOIN continuity_room.story_events AS b ON b.event_id = f.event_id_b
WHERE f.severity IN ('high', 'critical');

-- Marketing: spoiler-safe aggregate counts only, no characters/explanations.
CREATE VIEW IF NOT EXISTS continuity_room.vw_marketing_safe AS
SELECT
    script_id,
    episode_a AS episode,
    flag_type,
    severity,
    count() AS flag_count
FROM
(
    SELECT f.script_id AS script_id, f.flag_type AS flag_type, f.severity AS severity, a.episode AS episode_a
    FROM continuity_room.continuity_flags AS f
    LEFT JOIN continuity_room.story_events AS a ON a.event_id = f.event_id_a
)
GROUP BY script_id, episode_a, flag_type, severity;
