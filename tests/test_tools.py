# Copyright 2026 MSPbots.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""tools/list snapshot and the automated cases from docs/tickets/PRD-21329.ac.json (TC1-TC15)."""

import asyncio
import json

import httpx
import pytest

from neon_mcp import api_client
from neon_mcp.api_client import NeonCredentials
from neon_mcp.server import INSTRUCTIONS, _credentials_var, create_mcp_server

CREDS = NeonCredentials("key-123")

# Tool names are a public contract: existing agents and tenant connections depend on them.
# Changing this snapshot (or the required-argument sets) is a breaking change (SOP §13).
EMPTY: set[str] = set()
PID = {"project_id"}
PB = {"project_id", "branch_id"}

EXPECTED_TOOLS: dict[str, set[str]] = {
    "neon_list_projects": EMPTY,
    "neon_get_project": PID,
    "neon_list_branches": PID,
    "neon_get_branch": PB,
    "neon_create_branch": PID,
    "neon_delete_branch": PB,
    "neon_list_endpoints": PID,
    "neon_get_endpoint": {"project_id", "endpoint_id"},
    "neon_list_databases": PB,
    "neon_create_database": PB | {"database_name", "owner_name"},
    "neon_list_roles": PB,
    "neon_create_role": PB | {"role_name"},
    "neon_get_connection_uri": PID | {"database_name", "role_name"},
    "neon_list_operations": PID,
    "neon_get_operation": {"project_id", "operation_id"},
}


class Recorder:
    """Mock transport: replies by method + path below /api/v2/."""

    def __init__(self, routes=None, default=None):
        self.requests: list[httpx.Request] = []
        self.routes = routes or {}
        self.default = default if default is not None else {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/api/v2/")
        reply = self.routes.get(f"{request.method} {path}", self.routes.get(path, self.default))
        if callable(reply):
            return reply(request)
        return httpx.Response(200, json=reply)

    def calls(self, path: str, method: str | None = None) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == f"/api/v2/{path}" and (method is None or r.method == method)]


def body(request: httpx.Request):
    return json.loads(request.content) if request.content else None


async def _call(monkeypatch, recorder: Recorder, tool: str, args: dict):
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    monkeypatch.setattr(api_client, "_get_shared_http_client", lambda: http)
    ctx = _credentials_var.set(CREDS)
    try:
        content, _ = await create_mcp_server().call_tool(tool, args)
    finally:
        _credentials_var.reset(ctx)
    return json.loads(content[0].text)


def test_tools_list_matches_snapshot():
    async def run():
        mcp = create_mcp_server()
        tools = await mcp.list_tools()
        return {t.name: set(t.inputSchema.get("required") or []) for t in tools}

    assert asyncio.run(run()) == EXPECTED_TOOLS
    assert len(EXPECTED_TOOLS) == 15  # matches the technical design's Change list


def test_instructions_are_reasonably_sized():
    assert 0 < len(INSTRUCTIONS) <= 1500


# ---- TC1/TC2 (AC1): projects ------------------------------------------------


async def test_list_projects_returns_mocked_list(monkeypatch):
    rows = [{"id": "p1", "name": "demo", "region_id": "aws-us-east-2", "created_at": "2026-01-01T00:00:00Z"}]
    rec = Recorder({"projects": {"projects": rows}})
    result = await _call(monkeypatch, rec, "neon_list_projects", {})
    assert result["projects"] == rows and result["count"] == 1


async def test_list_projects_passes_cursor_and_limit(monkeypatch):
    rec = Recorder({"projects": {"projects": []}})
    await _call(monkeypatch, rec, "neon_list_projects", {"cursor": "abc", "limit": 5})
    params = rec.requests[0].url.params
    assert (params["cursor"], params["limit"]) == ("abc", "5")


# ---- TC3 (AC2): branches -----------------------------------------------------


async def test_list_branches_returns_fields(monkeypatch):
    rows = [{"id": "br-1", "name": "main", "parent_id": None, "default": True, "protected": False, "current_state": "ready"}]
    rec = Recorder({"projects/p1/branches": {"branches": rows}})
    result = await _call(monkeypatch, rec, "neon_list_branches", {"project_id": "p1"})
    assert result["branches"] == rows


# ---- TC4/TC5/TC6 (AC3/AC4/AC5): branch create/delete -------------------------


async def test_create_branch_returns_id_and_operations(monkeypatch):
    reply = {"branch": {"id": "br-2"}, "operations": [{"id": "op-1", "status": "running"}]}
    rec = Recorder({"POST projects/p1/branches": reply})
    result = await _call(monkeypatch, rec, "neon_create_branch", {"project_id": "p1", "branch_name": "feature"})
    assert result["branch"]["id"] == "br-2" and result["operations"][0]["id"] == "op-1"
    assert body(rec.requests[0]) == {"branch": {"name": "feature"}}


async def test_delete_branch_without_confirm_is_rejected(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "neon_delete_branch", {"project_id": "p1", "branch_id": "br-2"})
    assert result["done"] is False and rec.requests == []


async def test_delete_branch_with_confirm_calls_delete(monkeypatch):
    rec = Recorder({"DELETE projects/p1/branches/br-2": {"branch": {"id": "br-2"}, "operations": [{"id": "op-2"}]}})
    result = await _call(monkeypatch, rec, "neon_delete_branch", {"project_id": "p1", "branch_id": "br-2", "confirm": True})
    assert result["operations"][0]["id"] == "op-2"
    assert rec.calls("projects/p1/branches/br-2", "DELETE")


# ---- TC7 (AC6): endpoints -----------------------------------------------------


async def test_list_endpoints_returns_fields(monkeypatch):
    rows = [{"id": "ep-1", "branch_id": "br-1", "type": "read_write", "current_state": "active"}]
    rec = Recorder({"projects/p1/endpoints": {"endpoints": rows}})
    result = await _call(monkeypatch, rec, "neon_list_endpoints", {"project_id": "p1"})
    assert result["endpoints"] == rows


# ---- TC8/TC9 (AC7/AC8): databases ---------------------------------------------


async def test_list_databases_returns_fields(monkeypatch):
    rows = [{"name": "main", "owner_name": "app"}]
    rec = Recorder({"projects/p1/branches/br-1/databases": {"databases": rows}})
    result = await _call(monkeypatch, rec, "neon_list_databases", {"project_id": "p1", "branch_id": "br-1"})
    assert result["databases"] == rows


async def test_create_database_returns_created_record(monkeypatch):
    rec = Recorder({"POST projects/p1/branches/br-1/databases": {"database": {"name": "app_db", "owner_name": "app"}}})
    result = await _call(
        monkeypatch, rec, "neon_create_database",
        {"project_id": "p1", "branch_id": "br-1", "database_name": "app_db", "owner_name": "app"},
    )
    assert result == {"name": "app_db", "owner_name": "app"}
    assert body(rec.requests[0]) == {"database": {"name": "app_db", "owner_name": "app"}}


# ---- TC10/TC11 (AC9/AC10): roles -----------------------------------------------


async def test_list_roles_returns_fields(monkeypatch):
    rows = [{"name": "app", "protected": False}]
    rec = Recorder({"projects/p1/branches/br-1/roles": {"roles": rows}})
    result = await _call(monkeypatch, rec, "neon_list_roles", {"project_id": "p1", "branch_id": "br-1"})
    assert result["roles"] == rows


async def test_create_role_password_not_logged(monkeypatch, caplog):
    import logging

    rec = Recorder({"POST projects/p1/branches/br-1/roles": {"role": {"name": "app", "password": "s3cret-pw"}}})
    caplog.set_level(logging.DEBUG)
    result = await _call(monkeypatch, rec, "neon_create_role", {"project_id": "p1", "branch_id": "br-1", "role_name": "app"})
    assert result["password"] == "s3cret-pw"  # surfaced once, directly in the tool result
    assert "s3cret-pw" not in caplog.text  # never logged


# ---- TC12/TC13 (AC11/AC14): connection URI --------------------------------------


async def test_get_connection_uri_returns_uri(monkeypatch):
    rec = Recorder({"projects/p1/connection_uri": {"uri": "postgresql://app:pw@host/app_db"}})
    result = await _call(
        monkeypatch, rec, "neon_get_connection_uri",
        {"project_id": "p1", "database_name": "app_db", "role_name": "app", "branch_id": "br-1"},
    )
    assert result["uri"] == "postgresql://app:pw@host/app_db"
    params = rec.requests[0].url.params
    assert (params["database_name"], params["role_name"], params["branch_id"]) == ("app_db", "app", "br-1")


async def test_get_connection_uri_not_found_is_structured(monkeypatch):
    rec = Recorder({"projects/p1/connection_uri": lambda r: httpx.Response(404, json={"message": "role not found"})})
    result = await _call(
        monkeypatch, rec, "neon_get_connection_uri", {"project_id": "p1", "database_name": "x", "role_name": "y"}
    )
    assert result["error"]["code"] == "not_found"


# ---- TC14/TC15 (AC12): operations -----------------------------------------------


async def test_get_operation_returns_status(monkeypatch):
    rec = Recorder({"projects/p1/operations/op-1": {"operation": {"id": "op-1", "status": "finished"}}})
    result = await _call(monkeypatch, rec, "neon_get_operation", {"project_id": "p1", "operation_id": "op-1"})
    assert result["status"] == "finished"


async def test_list_operations_returns_recent(monkeypatch):
    rows = [{"id": "op-1", "status": "finished"}, {"id": "op-2", "status": "running"}]
    rec = Recorder({"projects/p1/operations": {"operations": rows}})
    result = await _call(monkeypatch, rec, "neon_list_operations", {"project_id": "p1"})
    assert result["operations"] == rows


# ---- invalid argument envelope (required field missing) -----------------------


async def test_missing_required_argument_is_invalid_argument(monkeypatch):
    result = await _call(monkeypatch, Recorder(), "neon_get_project", {})
    assert result["error"]["code"] == "invalid_argument" and result["error"]["retryable"] is False
