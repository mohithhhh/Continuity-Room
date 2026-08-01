# Continuity Room

Continuity Room is an AI script supervisor: it reads new script drafts,
cross-checks characters, props, and timelines against production history,
and flags contradictions on a live Grafana dashboard before they hit set.

It's built as three separately-privileged agents on **Google's Agent
Development Kit (ADK)** and **Gemini**, backed by **ClickHouse**, with
**Grafana** as the only surface a human ever looks at.

Built for the Agentic Cinema hackathon (Grafana partner track).

## Architecture

```
                 ┌─────────────────────┐
  script text →  │ Technical Producer   │  Gemini structured extraction
                 │ (ingestion)          │  → INSERT story_events
                 └──────────┬───────────┘  (clickhouse-connect, write-only)
                            │ script_id
                            ▼
                 ┌─────────────────────┐
                 │ Director              │  Read-only ClickHouse MCP server
                 │ (analysis)            │  (list_databases/list_tables/run_query)
                 └──────────┬───────────┘  → structured ContinuityReport
                            │ report JSON
                            ▼
                 ┌─────────────────────┐
                 │ Studio Head           │  INSERT continuity_flags + audit_log
                 │ (governance)          │  (clickhouse-connect, the only writer
                 └──────────┬───────────┘   of audit_log), RBAC views
                            │
                            ▼
                     Grafana dashboard
              (panels + alert rule read continuity_flags)
```

Each agent is a genuinely separate `google.adk.agents.LlmAgent` object with
its own, distinct tool bindings decided at construction time — not one
agent with access to everything:

| Agent | ADK object | Tools bound | Can write | Can read |
|---|---|---|---|---|
| Technical producer | [`backend/app/agents/producer.py`](backend/app/agents/producer.py) | none (pure Gemini structured extraction) | `story_events` only, via a single deterministic Python insert path | nothing (no query tool at all) |
| Director | [`backend/app/agents/director.py`](backend/app/agents/director.py) | `McpToolset` bound to the official ClickHouse MCP server, `tool_filter=["list_databases","list_tables","run_query"]` | nothing — no write tool exists in its tool list, and the MCP server subprocess itself is launched with `CLICKHOUSE_ALLOW_WRITE_ACCESS` hardcoded `"false"` | `story_events`, `continuity_flags` (read-only) |
| Studio head | [`backend/app/agents/studio_head.py`](backend/app/agents/studio_head.py) | one `FunctionTool` (`persist_report`) | `continuity_flags`, and **only this module** writes `audit_log` | role-scoped ClickHouse views (`vw_writers_room`, `vw_legal_standards`, `vw_marketing_safe`) |

The three are orchestrated as an explicit graph in
[`backend/app/agents/orchestrator.py`](backend/app/agents/orchestrator.py):
`run_technical_producer → run_director → run_studio_head`, each running its
own ADK `Runner` (see [`backend/app/agents/runtime.py`](backend/app/agents/runtime.py)).
This is deliberate explicit Python control flow rather than a single ADK
`SequentialAgent` wrapper — see the docstring at the top of
`orchestrator.py` for why (short version: the ClickHouse writes are
deterministic Python triggered after each agent's *validated* structured
output, not something we trust an LLM tool-call to reconstruct correctly —
that matters a lot for a table an audit trail depends on).

### Where Google Cloud is actually called

- [`backend/app/agents/producer.py`](backend/app/agents/producer.py) — `LlmAgent(model=..., output_schema=ExtractionResult, ...)`, run via `Runner.run_async` in [`runtime.py`](backend/app/agents/runtime.py). This is the Gemini call that turns raw script text into structured events.
- [`backend/app/agents/director.py`](backend/app/agents/director.py) — another `LlmAgent`, this one with a real `McpToolset` bound to the ClickHouse MCP server; Gemini decides which read-only queries to run and reasons over the results to produce the continuity report.
- [`backend/app/agents/studio_head.py`](backend/app/agents/studio_head.py) — `LlmAgent` with a bound `FunctionTool`; Gemini calls `persist_report` with the director's report.
- All three read `GOOGLE_API_KEY` / `GOOGLE_GENAI_USE_VERTEXAI` / `GOOGLE_CLOUD_PROJECT` from the environment (loaded in [`backend/app/config.py`](backend/app/config.py)) — set `GOOGLE_GENAI_USE_VERTEXAI=true` to route through Vertex AI instead of the Gemini API directly.

### Where Grafana is actually called

- [`infra/grafana/dashboards/continuity_room.json`](infra/grafana/dashboards/continuity_room.json) — the dashboard as code: open flags by severity, a timeline of flags per episode, and a full drill-down table.
- [`infra/grafana/alerting/continuity_alert.yaml`](infra/grafana/alerting/continuity_alert.yaml) — the alert rule as code: fires when a `continuity_flags` row with severity `high`/`critical` appears in the last 5 minutes.
- [`backend/scripts/provision_grafana.py`](backend/scripts/provision_grafana.py) — a real MCP client (`mcp.ClientSession` over stdio) that launches the official `mcp-grafana` server and calls its `update_dashboard` and `alerting_manage_rules` tools to push the above into a live Grafana Cloud stack. Datasource/folder creation uses Grafana's plain HTTP API directly (mcp-grafana doesn't expose datasource CRUD as an MCP tool as of v1.0.0).
- [`backend/app/api/main.py`](backend/app/api/main.py) — `/api/config` serves the live dashboard URL to the frontend.

## Data model (ClickHouse)

Full DDL: [`backend/db/ddl.sql`](backend/db/ddl.sql).

- `story_events` — one row per extracted event (script_id, episode, scene, character, location, time_of_day, props, state_changes, raw_excerpt, ingested_at). Written only by the technical producer.
- `continuity_flags` — one row per detected contradiction (event_id_a, event_id_b, flag_type, severity, explanation, status, created_at). Written only by the studio head, from the director's report. This is the table Grafana reads.
- `audit_log` — (actor_agent, action, target, viewer_role, timestamp). Written only by the studio head, for every report generated and every role-scoped view accessed.
- `vw_writers_room` / `vw_legal_standards` / `vw_marketing_safe` — SQL views over the two tables above that encode the three RBAC audiences (full detail / risk-flagged-only / spoiler-safe aggregate counts).

## Repo layout

```
backend/    FastAPI app + the three ADK agents + ClickHouse DDL/init
  app/agents/     producer.py, director.py, studio_head.py, orchestrator.py, runtime.py
  app/api/        FastAPI app (main.py)
  app/clickhouse/ native clickhouse-connect client (write path)
  db/             ddl.sql, init_db.py
  scripts/        provision_grafana.py
frontend/   Minimal React+Vite single page (paste/upload script, run pipeline, status, Grafana link)
infra/
  docker/         docker-compose.yml — local ClickHouse for dev
  grafana/        dashboard JSON, alert rule YAML, datasource/dashboard provisioning YAML
  cloudrun/       deploy.sh
data/seed_screenplay/  synthetic 3-episode demo script with 3 planted continuity errors
Dockerfile  single-service build: React static build + FastAPI, for Cloud Run
```

## Setup & run (local dev)

### Prerequisites

- Python 3.11+, Node 20+, Docker (for local ClickHouse)
- A Gemini API key ([aistudio.google.com](https://aistudio.google.com/apikey)), or a GCP project with Vertex AI enabled

### 1. Configure environment

```bash
cp .env.example .env
# fill in at least GOOGLE_API_KEY; leave CLICKHOUSE_* at their local-docker
# defaults for now
```

### 2. Start local ClickHouse and apply the schema

```bash
cd infra/docker && docker compose up -d && cd ../..

cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m db.init_db
```

### 3. Run the backend

```bash
# from backend/, with .venv activated
uvicorn app.api.main:app --reload --port 8080
```

### 4. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open the printed local URL, paste a scene (or upload one of the files in
`data/seed_screenplay/`), and click **Run pipeline**. Ingest all three
episodes to see the three planted continuity errors surface as flags — see
[`data/seed_screenplay/README.md`](data/seed_screenplay/README.md) for what
they are and why.

### 5. Grafana

You need a Grafana Cloud stack (free tier is fine) with the
[ClickHouse data source plugin](https://grafana.com/grafana/plugins/grafana-clickhouse-datasource/)
installed. Set `GRAFANA_URL` and `GRAFANA_SERVICE_ACCOUNT_TOKEN` in `.env`
(the service account needs the Admin role to create datasources, folders,
dashboards, and alert rules), then:

```bash
cd backend && source .venv/bin/activate
python -m scripts.provision_grafana
```

This creates the ClickHouse datasource, the "Continuity Room" folder, the
dashboard, and the alert rule, using the Grafana MCP server (`mcp-grafana`,
launched via `uvx` — install [`uv`](https://docs.astral.sh/uv/) if you don't
have it). If you'd rather do it by hand, import
`infra/grafana/dashboards/continuity_room.json` directly in the Grafana UI
and use `infra/grafana/alerting/continuity_alert.yaml` as a reference for
the alert rule.

The alert's contact point is a webhook by default (`ALERT_WEBHOOK_URL` in
`.env`) — point it at anything that can receive a POST for the demo
(e.g. a temporary [webhook.site](https://webhook.site) URL), or switch it to
email (`ALERT_EMAIL_ADDRESS`) per the comment in
`infra/grafana/alerting/continuity_alert.yaml`.

## Deploy to Cloud Run

```bash
# fill in GCP_PROJECT_ID / GCP_REGION / ARTIFACT_REGISTRY_REPO in .env first
./infra/cloudrun/deploy.sh
```

This builds the single-container image (React static build + FastAPI) via
Cloud Build, syncs `GOOGLE_API_KEY` / `CLICKHOUSE_PASSWORD` /
`GRAFANA_SERVICE_ACCOUNT_TOKEN` into Secret Manager, and deploys to Cloud
Run with those wired in as secrets (never as plain env vars, never
hardcoded). Review the script before running it — it creates billed cloud
resources.

## License

MIT — see [LICENSE](LICENSE).
