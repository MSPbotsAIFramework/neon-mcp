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
"""Branches: Neon's instant copy-on-write Postgres branches inside a project."""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import NeonClient
from ._common import (
    DESTRUCTIVE,
    READ_ONLY,
    WRITES,
    BranchId,
    ClientFactory,
    Confirm,
    Cursor,
    Limit,
    ProjectId,
    compact,
    list_cursor,
    not_confirmed,
    run_tool,
    unwrap,
)


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def neon_list_branches(project_id: ProjectId, limit: Limit = None, cursor: Cursor = None) -> str:
        """List a project's branches: id, name, parent branch id, default/protected flags, state."""

        async def action(client: NeonClient) -> dict:
            return await list_cursor(client, f"projects/{project_id}/branches", "branches", {}, limit, cursor)

        return await run_tool("neon_list_branches", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def neon_get_branch(project_id: ProjectId, branch_id: BranchId) -> str:
        """Get one branch's details and current state."""

        async def action(client: NeonClient):
            return unwrap(await client.get(f"projects/{project_id}/branches/{branch_id}"), "branch")

        return await run_tool("neon_get_branch", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def neon_create_branch(
        project_id: ProjectId,
        branch_name: Annotated[str | None, Field(description="Name for the new branch; Neon generates one if omitted.")] = None,
        parent_id: Annotated[str | None, Field(description="Source branch id to copy from; the project's default branch if omitted.")] = None,
    ) -> str:
        """Create a branch (instant copy-on-write). Only when the user explicitly asks.

        Branch creation is asynchronous: poll neon_get_operation with the returned operation
        id(s) until the status is terminal before using the new branch.
        """

        async def action(client: NeonClient):
            body = {"branch": compact({"name": branch_name, "parent_id": parent_id})}
            return await client.post(f"projects/{project_id}/branches", body)

        return await run_tool("neon_create_branch", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def neon_delete_branch(project_id: ProjectId, branch_id: BranchId, confirm: Confirm = None) -> str:
        """Permanently delete a branch and everything on it. Irreversible; needs confirm: true.

        Only when the user explicitly asks and has approved deleting this exact branch.
        """

        async def action(client: NeonClient):
            if confirm is not True:
                return not_confirmed(f"Permanently delete branch {branch_id} in project {project_id}")
            return await client.delete(f"projects/{project_id}/branches/{branch_id}")

        return await run_tool("neon_delete_branch", client_factory, action)
