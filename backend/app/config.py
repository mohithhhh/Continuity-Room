from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

# google-genai (used internally by every ADK LlmAgent) reads
# GOOGLE_API_KEY / GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_CLOUD_PROJECT /
# GOOGLE_CLOUD_LOCATION straight out of the process environment, not from
# our Settings object below — load .env into os.environ first so both paths
# see the same values.
load_dotenv(REPO_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", extra="ignore", case_sensitive=False
    )

    # Gemini / Vertex AI
    google_genai_use_vertexai: bool = False
    google_api_key: str | None = None
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"
    gemini_model: str = "gemini-3.5-flash-lite"

    # ClickHouse — technical producer agent's write path (clickhouse-connect)
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "continuity_room"
    clickhouse_secure: bool = False

    # ClickHouse MCP server — director agent's read-only path
    clickhouse_allow_write_access: bool = False

    # Grafana Cloud
    grafana_url: str | None = None
    grafana_service_account_token: str | None = None

    # Alerting
    alert_webhook_url: str | None = None
    alert_email_address: str | None = None

    # App
    backend_port: int = 8080
    frontend_origin: str = "http://localhost:5173"


settings = Settings()
