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
"""FastMCP factory and the per-request credential middleware."""

import contextvars
import re
import uuid
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ._arguments import EnvelopeFastMCP
from .api_client import NeonClient, NeonCredentials
from .config import Settings

HEADER_API_KEY = "X-Neon-API-Key"
REQUIRED_HEADERS = [HEADER_API_KEY]

_PLACEHOLDER = re.compile(r"^\$\{.*\}$")

# Per-request isolation: the middleware sets these for the duration of one
# HTTP request and resets them in `finally`. Nothing credential-related is
# ever stored at module level.
_credentials_var: contextvars.ContextVar[NeonCredentials | None] = contextvars.ContextVar(
    "neon_credentials", default=None
)
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("neon_request_id", default="-")

INSTRUCTIONS = (
    "Neon is a serverless Postgres platform. This connector manages one Neon account's "
    "infrastructure (projects, branches, compute endpoints, databases, roles) through Neon's "
    "control-plane REST API; it does not run SQL against the data a branch holds.\n"
    "Usage:\n"
    "- Find the project first: neon_list_projects(); project ids feed every other tool.\n"
    "- Branching is the core workflow: neon_create_branch(project_id) copies a branch "
    "instantly; poll neon_get_operation with the returned operation id until its status is "
    "terminal before using the new branch. neon_delete_branch needs confirm: true.\n"
    "- Use neon_create_database / neon_create_role to set up a database and owner on a "
    "branch, then neon_get_connection_uri for a ready-to-use Postgres connection string.\n"
    "- neon_create_role's response may include a one-time generated password: show it to the "
    "user immediately, it is never stored or logged.\n"
    "Create and delete tools change the account's infrastructure: call them only when the "
    "user explicitly asks. neon_delete_branch is permanent and also needs confirm: true."
)


def get_client_from_context() -> NeonClient | None:
    """The client for the current request, or None outside a request."""
    credentials = _credentials_var.get()
    if credentials is None:
        return None
    return NeonClient(credentials)


def _clean(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text or _PLACEHOLDER.match(text):
        return None
    return text


class GatewayCredentialsMiddleware:
    """Reads X-Neon-API-Key on /mcp requests; 401 when missing."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        api_key = _clean(request.headers.get(HEADER_API_KEY))
        if not api_key:
            await JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": f"Missing header: {HEADER_API_KEY}",
                    "required_headers": REQUIRED_HEADERS,
                },
                status_code=401,
            )(scope, receive, send)
            return

        request_id = (request.headers.get("x-request-id") or "").strip()[:64] or uuid.uuid4().hex[:12]
        creds_token = _credentials_var.set(NeonCredentials(api_key))
        rid_token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _credentials_var.reset(creds_token)
            request_id_var.reset(rid_token)


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    """Build the FastMCP server and register every tool."""
    mcp = EnvelopeFastMCP(
        name="neon-mcp",
        instructions=INSTRUCTIONS,
        # The service sits behind the gateway, so Host is never localhost;
        # DNS-rebinding protection would reject those requests with 421.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        stateless_http=True,
    )

    client_factory: Callable[[], NeonClient | None] = get_client_from_context

    from .tools import branches, connection, databases, endpoints, operations, projects, roles

    for module in (projects, branches, endpoints, databases, roles, connection, operations):
        module.register(mcp, client_factory)

    return mcp
