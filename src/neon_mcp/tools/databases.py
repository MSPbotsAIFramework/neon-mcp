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
"""Databases inside a branch."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import NeonClient
from ._common import READ_ONLY, WRITES, BranchId, ClientFactory, Cursor, Limit, ProjectId, list_cursor, run_tool, unwrap


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def neon_list_databases(project_id: ProjectId, branch_id: BranchId, limit: Limit = None, cursor: Cursor = None) -> str:
        """List a branch's databases: name and owning role."""

        async def action(client: NeonClient) -> dict:
            return await list_cursor(
                client, f"projects/{project_id}/branches/{branch_id}/databases", "databases", {}, limit, cursor
            )

        return await run_tool("neon_list_databases", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def neon_create_database(
        project_id: ProjectId,
        branch_id: BranchId,
        database_name: Annotated[str, Field(description="Name for the new database.", min_length=1)],
        owner_name: Annotated[str, Field(description="Role that owns the new database.", min_length=1)],
    ) -> str:
        """Create a database on a branch with a name and an owning role. Only when the user explicitly asks."""

        async def action(client: NeonClient):
            body = {"database": {"name": database_name, "owner_name": owner_name}}
            return unwrap(await client.post(f"projects/{project_id}/branches/{branch_id}/databases", body), "database")

        return await run_tool("neon_create_database", client_factory, action)
