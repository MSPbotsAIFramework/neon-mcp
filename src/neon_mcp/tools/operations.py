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
"""Operations: Neon's async job tracking for branch/database/role changes."""

from mcp.server.fastmcp import FastMCP

from ..api_client import NeonClient
from ._common import READ_ONLY, ClientFactory, Cursor, Limit, OperationId, ProjectId, list_cursor, run_tool, unwrap


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def neon_list_operations(project_id: ProjectId, limit: Limit = None, cursor: Cursor = None) -> str:
        """List a project's recent operations (async jobs), newest first."""

        async def action(client: NeonClient) -> dict:
            return await list_cursor(client, f"projects/{project_id}/operations", "operations", {}, limit, cursor)

        return await run_tool("neon_list_operations", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def neon_get_operation(project_id: ProjectId, operation_id: OperationId) -> str:
        """Get one operation's current status; poll this after create/delete calls until it is terminal."""

        async def action(client: NeonClient):
            return unwrap(await client.get(f"projects/{project_id}/operations/{operation_id}"), "operation")

        return await run_tool("neon_get_operation", client_factory, action)
