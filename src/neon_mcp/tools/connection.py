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
"""Ready-to-use Postgres connection strings for a project/branch/database/role."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import NeonClient
from ._common import READ_ONLY, ClientFactory, ProjectId, compact, run_tool


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def neon_get_connection_uri(
        project_id: ProjectId,
        database_name: Annotated[str, Field(description="Database name.", min_length=1)],
        role_name: Annotated[str, Field(description="Role (Postgres user) name.", min_length=1)],
        branch_id: Annotated[str | None, Field(description="Branch id; the project's default branch if omitted.")] = None,
        pooled: Annotated[bool | None, Field(description="true for a connection-pooled URI.")] = None,
    ) -> str:
        """Get a ready-to-use Postgres connection URI for a database/role, to connect over the wire protocol.

        The returned URI contains the role's password: show it to the user, do not log it
        elsewhere. This connector manages infrastructure only — it does not itself run SQL
        against the data on the other end of this URI.
        """

        async def action(client: NeonClient):
            params = compact(
                {"database_name": database_name, "role_name": role_name, "branch_id": branch_id, "pooled": pooled}
            )
            return await client.get(f"projects/{project_id}/connection_uri", params)

        return await run_tool("neon_get_connection_uri", client_factory, action)
