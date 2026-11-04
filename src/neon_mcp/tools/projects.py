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
"""Projects: the top-level Neon resource; everything else lives under one."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import NeonClient
from ._common import READ_ONLY, ClientFactory, Cursor, Limit, ProjectId, list_cursor, run_tool, unwrap


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def neon_list_projects(
        limit: Limit = None,
        cursor: Cursor = None,
        search: Annotated[str | None, Field(description="Filter by project name or id substring.")] = None,
    ) -> str:
        """List the Neon projects in this account; id/name/region/created_at per project."""

        async def action(client: NeonClient) -> dict:
            return await list_cursor(client, "projects", "projects", {"search": search}, limit, cursor)

        return await run_tool("neon_list_projects", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def neon_get_project(project_id: ProjectId) -> str:
        """Get one Neon project's settings (region, Postgres version, default branch, limits)."""

        async def action(client: NeonClient):
            return unwrap(await client.get(f"projects/{project_id}"), "project")

        return await run_tool("neon_get_project", client_factory, action)
