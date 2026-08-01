import clickhouse_connect
from clickhouse_connect.driver.client import Client

from app.config import settings


def get_client() -> Client:
    """Native clickhouse-connect client, used only by the technical producer
    agent (story_events writes) and the studio head agent (continuity_flags /
    audit_log writes, vw_* reads). The director agent never imports this
    module — its only path to ClickHouse is the read-only MCP server.
    """
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        secure=settings.clickhouse_secure,
    )
