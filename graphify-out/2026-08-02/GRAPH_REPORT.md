# Graph Report - .  (2026-08-02)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 153 nodes · 225 edges · 18 communities (16 shown, 2 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 3 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c51a6759`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- orchestrator.py
- studio_head.py
- provision_grafana.py
- compilerOptions
- main.py
- package.json
- api.ts
- devDependencies
- init_db.py
- deploy.sh
- vercel.json

## God Nodes (most connected - your core abstractions)
1. `compilerOptions` - 12 edges
2. `main()` - 10 edges
3. `run_pipeline()` - 9 edges
4. `run_agent_once()` - 9 edges
5. `get_client()` - 9 edges
6. `ContinuityReport` - 8 edges
7. `run_technical_producer()` - 7 edges
8. `get_role_scoped_view()` - 7 edges
9. `PipelineResult` - 6 edges
10. `run_studio_head()` - 6 edges

## Surprising Connections (you probably didn't know these)
- `PipelineStageResult` --uses--> `ContinuityReport`  [INFERRED]
  backend/app/agents/orchestrator.py → backend/app/schemas.py
- `PipelineResult` --uses--> `ContinuityReport`  [INFERRED]
  backend/app/agents/orchestrator.py → backend/app/schemas.py
- `run_pipeline()` --calls--> `run_director()`  [EXTRACTED]
  backend/app/agents/orchestrator.py → backend/app/agents/director.py
- `RunPipelineRequest` --uses--> `PipelineResult`  [INFERRED]
  backend/app/api/main.py → backend/app/agents/orchestrator.py
- `run_pipeline()` --calls--> `run_technical_producer()`  [EXTRACTED]
  backend/app/agents/orchestrator.py → backend/app/agents/producer.py

## Import Cycles
- None detected.

## Communities (18 total, 2 thin omitted)

### Community 0 - "orchestrator.py"
Cohesion: 0.14
Nodes (21): ContinuityReport, Director agent — analysis. Privilege boundary: this agent's ONLY path to…, run_director(), Explicit three-agent pipeline graph. Each stage below is a fully separate ADK…, Technical producer agent — ingestion. Privilege boundary: this is the ONLY…, Extracts structured events from raw script text via Gemini, then writes them to…, The only write path into story_events. Deliberately deterministic Python rather…, run_technical_producer() (+13 more)

### Community 1 - "studio_head.py"
Cohesion: 0.16
Nodes (16): get_role_scoped_view(), _persist_flags(), persist_report(), ContinuityReport, ViewerRole, Studio head agent — governance. Privilege boundary: this is the ONLY module in…, Runs the studio head agent on a director report, returning its final…, Deterministic RBAC read path used by the API layer (independent of the agent… (+8 more)

### Community 2 - "provision_grafana.py"
Cohesion: 0.22
Nodes (18): call_mcp_tool(), _clickhouse_datasource_payload(), ensure_clickhouse_datasource(), ensure_contact_point(), ensure_folder(), ensure_notification_policy(), find_existing_rule_uid(), get_org_id() (+10 more)

### Community 3 - "compilerOptions"
Cohesion: 0.11
Nodes (17): compilerOptions, isolatedModules, jsx, lib, module, moduleResolution, noEmit, resolveJsonModule (+9 more)

### Community 4 - "main.py"
Cohesion: 0.17
Nodes (16): PipelineResult, PipelineStageResult, BaseModel, Runs technical producer -> director -> studio head in sequence against one…, run_pipeline(), get_config(), get_flags(), health() (+8 more)

### Community 5 - "package.json"
Cohesion: 0.14
Nodes (13): dependencies, react, react-dom, name, private, scripts, build, dev (+5 more)

### Community 6 - "api.ts"
Cohesion: 0.22
Nodes (10): ContinuityFlagDraft, ContinuityReport, FlagType, getConfig(), PipelineResult, PipelineStageResult, runPipeline(), Severity (+2 more)

### Community 7 - "devDependencies"
Cohesion: 0.18
Nodes (11): devDependencies, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react, @types/react, @types/react-dom (+3 more)

### Community 8 - "init_db.py"
Cohesion: 0.67
Nodes (3): main(), Applies backend/db/ddl.sql against the configured ClickHouse instance. Run once…, statements()

## Knowledge Gaps
- **35 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+30 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_client()` connect `studio_head.py` to `orchestrator.py`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Why does `get_role_scoped_view()` connect `studio_head.py` to `main.py`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Why does `run_agent_once()` connect `orchestrator.py` to `studio_head.py`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **What connects `name`, `private`, `version` to the rest of the system?**
  _35 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `orchestrator.py` be split into smaller, more focused modules?**
  _Cohesion score 0.13538461538461538 - nodes in this community are weakly interconnected._
- **Should `compilerOptions` be split into smaller, more focused modules?**
  _Cohesion score 0.1111111111111111 - nodes in this community are weakly interconnected._
- **Should `package.json` be split into smaller, more focused modules?**
  _Cohesion score 0.14285714285714285 - nodes in this community are weakly interconnected._