"""Provisions the Continuity Room Grafana dashboard and alert rule against a
live Grafana Cloud stack. This is the Grafana MCP server called from code —
dashboard and alert-rule writes go through `mcp-grafana`'s tools, not the
Grafana UI. Datasource and folder creation use Grafana's plain HTTP API
directly, because mcp-grafana (as of v1.0.0) doesn't expose datasource CRUD
as an MCP tool.

Requires `uv`/`uvx` on PATH (used to launch the mcp-grafana server) and
GRAFANA_URL / GRAFANA_SERVICE_ACCOUNT_TOKEN set in .env.

Run once:

    cd backend && source .venv/bin/activate && python -m scripts.provision_grafana
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = REPO_ROOT / "infra" / "grafana" / "dashboards" / "continuity_room.json"
CLICKHOUSE_DS_UID = "continuity-room-clickhouse"
FOLDER_TITLE = "Continuity Room"


def _require_grafana_config() -> None:
    if not settings.grafana_url or not settings.grafana_service_account_token:
        raise SystemExit(
            "GRAFANA_URL and GRAFANA_SERVICE_ACCOUNT_TOKEN must be set in .env "
            "before provisioning. See .env.example."
        )


def _grafana_client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.grafana_url,
        headers={"Authorization": f"Bearer {settings.grafana_service_account_token}"},
        timeout=30.0,
    )


def _clickhouse_datasource_payload() -> dict:
    return {
        "uid": CLICKHOUSE_DS_UID,
        "name": "Continuity Room ClickHouse",
        "type": "grafana-clickhouse-datasource",
        "access": "proxy",
        "jsonData": {
            "host": settings.clickhouse_host,
            "port": settings.clickhouse_port,
            # The plugin's `protocol` field is the ClickHouse wire protocol
            # ("http" or "native") — NOT the URL scheme. TLS is controlled
            # separately by `secure`. Setting protocol="https" here (an
            # earlier bug) makes the plugin send the wrong handshake bytes,
            # surfacing as a cryptic "unexpected packet" error at query time.
            "protocol": "http",
            "secure": settings.clickhouse_secure,
            "username": settings.clickhouse_user,
            "defaultDatabase": settings.clickhouse_database,
        },
        "secureJsonData": {"password": settings.clickhouse_password},
    }


def ensure_clickhouse_datasource(client: httpx.Client) -> str:
    """Idempotently ensures the ClickHouse datasource exists (creating or
    correcting it) via Grafana's HTTP API. Returns its uid."""
    resp = client.get(f"/api/datasources/uid/{CLICKHOUSE_DS_UID}")
    if resp.status_code == 200:
        existing = resp.json()
        payload = _clickhouse_datasource_payload()
        if existing.get("jsonData", {}).get("protocol") != payload["jsonData"]["protocol"]:
            resp = client.put(f"/api/datasources/uid/{CLICKHOUSE_DS_UID}", json=payload)
            resp.raise_for_status()
        return CLICKHOUSE_DS_UID

    resp = client.post("/api/datasources", json=_clickhouse_datasource_payload())
    resp.raise_for_status()
    return resp.json()["datasource"]["uid"]


def ensure_folder(client: httpx.Client) -> str:
    resp = client.get("/api/folders")
    resp.raise_for_status()
    for folder in resp.json():
        if folder["title"] == FOLDER_TITLE:
            return folder["uid"]
    resp = client.post("/api/folders", json={"title": FOLDER_TITLE})
    resp.raise_for_status()
    return resp.json()["uid"]


def get_org_id(client: httpx.Client) -> int:
    resp = client.get("/api/org")
    resp.raise_for_status()
    return resp.json()["id"]


CONTACT_POINT_NAME = "continuity-room-alerts"


def ensure_contact_point(client: httpx.Client) -> str:
    """Idempotently ensures the webhook contact point exists via Grafana's
    HTTP provisioning API — mcp-grafana's alerting_manage_routing tool is
    read-only as of v1.0.0 (it can list contact points but not create one),
    so this one piece has to go through the plain REST API rather than MCP.
    Returns the contact point name, used as a route's `receiver`."""
    resp = client.get("/api/v1/provisioning/contact-points")
    resp.raise_for_status()
    if any(cp["name"] == CONTACT_POINT_NAME for cp in resp.json()):
        return CONTACT_POINT_NAME

    if not settings.alert_webhook_url:
        raise SystemExit(
            "ALERT_WEBHOOK_URL must be set in .env to provision the contact point."
        )
    payload = {
        "name": CONTACT_POINT_NAME,
        "type": "webhook",
        "settings": {"url": settings.alert_webhook_url, "httpMethod": "POST"},
        "disableResolveMessage": False,
    }
    resp = client.post(
        "/api/v1/provisioning/contact-points",
        json=payload,
        headers={"X-Disable-Provenance": "true"},
    )
    resp.raise_for_status()
    return CONTACT_POINT_NAME


def ensure_notification_policy(client: httpx.Client, receiver: str) -> None:
    """Idempotently adds a nested route sending severity high/critical
    alerts to `receiver`, without touching the existing root policy or any
    other routes already configured on this stack."""
    resp = client.get("/api/v1/provisioning/policies")
    resp.raise_for_status()
    tree = resp.json()
    routes = tree.setdefault("routes", [])

    if any(r.get("receiver") == receiver for r in routes):
        return

    routes.append(
        {
            "receiver": receiver,
            "object_matchers": [["severity", "=~", "high|critical"]],
            "continue": False,
        }
    )
    resp = client.put(
        "/api/v1/provisioning/policies",
        json=tree,
        headers={"X-Disable-Provenance": "true"},
    )
    resp.raise_for_status()


async def call_mcp_tool(tool_name: str, arguments: dict):
    server_params = StdioServerParameters(
        command="uvx",
        args=["mcp-grafana"],
        env={
            "GRAFANA_URL": settings.grafana_url,
            "GRAFANA_SERVICE_ACCOUNT_TOKEN": settings.grafana_service_account_token,
        },
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if result.isError:
                tools = await session.list_tools()
                schema = next(
                    (t.inputSchema for t in tools.tools if t.name == tool_name), None
                )
                raise RuntimeError(
                    f"mcp-grafana tool '{tool_name}' returned an error: "
                    f"{result.content}\nExpected input schema: "
                    f"{json.dumps(schema, indent=2)}"
                )
            return result.content


async def provision_dashboard(clickhouse_ds_uid: str, folder_uid: str) -> None:
    dashboard_text = DASHBOARD_PATH.read_text().replace(
        "${DS_CLICKHOUSE}", clickhouse_ds_uid
    )
    dashboard = json.loads(dashboard_text)
    await call_mcp_tool(
        "update_dashboard",
        {
            "dashboard": dashboard,
            "folderUid": folder_uid,
            "message": "Provisioned by scripts/provision_grafana.py",
        },
    )
    print("Dashboard provisioned via Grafana MCP server (update_dashboard).")


ALERT_RULE_TITLE = "Continuity Room: high severity flag detected"


async def find_existing_rule_uid(folder_uid: str) -> str | None:
    result = await call_mcp_tool(
        "alerting_manage_rules", {"operation": "list", "folder_uid": folder_uid}
    )
    rules = json.loads(result[0].text)
    rules = rules if isinstance(rules, list) else rules.get("rules", [])
    for rule in rules:
        if rule.get("title") == ALERT_RULE_TITLE:
            return rule.get("uid") or rule.get("rule_uid")
    return None


async def provision_alert_rule(
    clickhouse_ds_uid: str, folder_uid: str, org_id: int, contact_point: str
) -> None:
    # alerting_manage_rules takes flat, snake_case top-level arguments — not
    # a nested "rule" object (that was our first, wrong guess; the schema
    # dump printed by call_mcp_tool's error path is what told us the real
    # shape).
    existing_uid = await find_existing_rule_uid(folder_uid)
    operation = "update" if existing_uid else "create"

    payload = {
            "operation": operation,
            "title": ALERT_RULE_TITLE,
            "rule_group": "continuity-room",
            "folder_uid": folder_uid,
            "org_id": org_id,
            "condition": "C",
            "data": [
                {
                    "refId": "A",
                    "datasourceUid": clickhouse_ds_uid,
                    "relativeTimeRange": {"from": 300, "to": 0},
                    "model": {
                        "rawSql": (
                            "SELECT count() AS new_high_severity_flags "
                            "FROM continuity_room.continuity_flags "
                            "WHERE severity IN ('high', 'critical') "
                            "AND created_at > now() - INTERVAL 5 MINUTE"
                        ),
                        "format": "table",
                        "refId": "A",
                    },
                },
                {
                    "refId": "C",
                    "datasourceUid": "__expr__",
                    "model": {
                        "type": "threshold",
                        "expression": "A",
                        "conditions": [{"evaluator": {"type": "gt", "params": [0]}}],
                        "refId": "C",
                    },
                },
            ],
            "no_data_state": "NoData",
            "exec_err_state": "Error",
            "for": "0s",
            "labels": {"severity": "high"},
            # Set directly on the rule (in addition to the severity-matching
            # policy route from ensure_notification_policy) so this rule's
            # notifications reach our contact point even if the policy tree
            # changes later.
            "notification_settings": {"receiver": contact_point},
            "annotations": {
                "summary": (
                    "A new continuity_flags row with severity high or "
                    "critical was inserted in the last 5 minutes."
                )
            },
    }
    if existing_uid:
        payload["rule_uid"] = existing_uid

    await call_mcp_tool("alerting_manage_rules", payload)
    print(f"Alert rule {operation}d via Grafana MCP server (alerting_manage_rules).")


def main() -> None:
    _require_grafana_config()
    with _grafana_client() as client:
        clickhouse_ds_uid = ensure_clickhouse_datasource(client)
        folder_uid = ensure_folder(client)
        org_id = get_org_id(client)
        contact_point = ensure_contact_point(client)
        ensure_notification_policy(client, contact_point)
    print(f"ClickHouse datasource uid: {clickhouse_ds_uid}")
    print(f"Folder uid: {folder_uid}")
    print(f"Org id: {org_id}")
    print(f"Contact point: {contact_point} -> {settings.alert_webhook_url}")
    asyncio.run(provision_dashboard(clickhouse_ds_uid, folder_uid))
    asyncio.run(provision_alert_rule(clickhouse_ds_uid, folder_uid, org_id, contact_point))


if __name__ == "__main__":
    main()
