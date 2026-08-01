from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agents.orchestrator import PipelineResult, run_pipeline
from app.agents.studio_head import get_role_scoped_view
from app.config import settings
from app.schemas import ViewerRole

app = FastAPI(title="Continuity Room API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunPipelineRequest(BaseModel):
    script_id: str
    raw_text: str


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config")
def get_config() -> dict:
    """Runtime config for the frontend — notably the live Grafana dashboard
    link, which we don't want to bake in at frontend build time (that would
    force a rebuild any time the Grafana stack URL changes)."""
    dashboard_url = f"{settings.grafana_url}/d/continuity-room" if settings.grafana_url else None
    return {"grafana_dashboard_url": dashboard_url}


@app.post("/api/pipeline/run", response_model=PipelineResult)
async def run_pipeline_endpoint(req: RunPipelineRequest) -> PipelineResult:
    if not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text must not be empty")
    return await run_pipeline(req.script_id, req.raw_text)


@app.get("/api/flags")
def get_flags(
    script_id: str = Query(...),
    role: ViewerRole = Query("writers_room"),
) -> list[dict]:
    return get_role_scoped_view(script_id, role)


# Cloud Run serves the built React app from this same container; the built
# frontend/dist directory is copied in at Dockerfile build time. In local
# dev the frontend runs separately via `npm run dev` and this mount is
# simply absent (no error — StaticFiles just isn't mounted).
_FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
