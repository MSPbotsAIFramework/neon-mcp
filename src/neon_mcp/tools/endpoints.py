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
"""Compute endpoints: the running Postgres instances attached to a project's branches."""

from mcp.server.fastmcp import FastMCP

from ..api_client import NeonClient
from ._common import READ_ONLY, ClientFactory, Cursor, EndpointId, Limit, ProjectId, list_cursor, run_tool, unwrap


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def neon_list_endpoints(project_id: ProjectId, limit: Limit = None, cursor: Cursor = None) -> str:
        """List a project's compute endpoints: id, branch id, type (read-write/read-only), state."""

        async def action(client: NeonClient) -> dict:
            return await list_cursor(client, f"projects/{project_id}/endpoints", "endpoints", {}, limit, cursor)

        return await run_tool("neon_list_endpoints", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def neon_get_endpoint(project_id: ProjectId, endpoint_id: EndpointId) -> str:
        """Get one compute endpoint's settings and current state."""

        async def action(client: NeonClient):
            return unwrap(await client.get(f"projects/{project_id}/endpoints/{endpoint_id}"), "endpoint")

        return await run_tool("neon_get_endpoint", client_factory, action)
