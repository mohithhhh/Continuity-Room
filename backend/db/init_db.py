"""Applies backend/db/ddl.sql against the configured ClickHouse instance.

Run once against a fresh ClickHouse (local docker-compose instance or a
ClickHouse Cloud instance) before running the pipeline:

    cd backend && source .venv/bin/activate && python -m db.init_db
"""

import sys
from pathlib import Path

import clickhouse_connect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings  # noqa: E402

DDL_PATH = Path(__file__).resolve().parent / "ddl.sql"


def statements(sql: str):
    # Strip full-line comments from the whole file BEFORE splitting on ";" —
    # several comments here contain semicolons mid-sentence, which would
    # otherwise fracture one statement into two.
    without_comments = "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )
    for raw in without_comments.split(";"):
        stripped = raw.strip()
        if stripped:
            yield stripped


def main() -> None:
    client = clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        secure=settings.clickhouse_secure,
    )
    ddl = DDL_PATH.read_text()
    for statement in statements(ddl):
        label = statement.split("\n", 1)[0][:70]
        print(f"-- {label}")
        client.command(statement)
    print(f"Schema applied to database '{settings.clickhouse_database}'.")


if __name__ == "__main__":
    main()
