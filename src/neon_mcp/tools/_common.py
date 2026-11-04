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
"""Shared argument types, the cursor-paging helper, confirmation and the error-handling wrapper."""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import dump_json_capped, error_envelope
from ..api_client import NeonClient, NeonError
from ..config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

logger = logging.getLogger("neon_mcp.tools")

ClientFactory = Callable[[], NeonClient | None]

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)

NOT_CONFIGURED = error_envelope(
    "not_configured", "Neon credentials are missing for this request (X-Neon-API-Key).", False
)

ProjectId = Annotated[str, Field(description="Neon project id, e.g. 'young-term-12345678'.", min_length=1)]
BranchId = Annotated[str, Field(description="Neon branch id, e.g. 'br-wispy-sky-12345678'.", min_length=1)]
EndpointId = Annotated[str, Field(description="Neon compute endpoint id.", min_length=1)]
OperationId = Annotated[str, Field(description="Neon operation id.", min_length=1)]
Cursor = Annotated[str | None, Field(description="Opaque pagination cursor from a previous call's next_cursor.")]
Limit = Annotated[
    int | None,
    Field(description=f"Records per page (default {DEFAULT_PAGE_SIZE}, max {MAX_PAGE_SIZE}).", ge=1, le=MAX_PAGE_SIZE),
]
Confirm = Annotated[bool | None, Field(description="Must be true, set only after the user approved this exact deletion.")]


def compact(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def unwrap(payload: Any, key: str) -> Any:
    """Neon wraps single records as {"branch": {...}}; return the record itself."""
    if isinstance(payload, dict) and key in payload:
        return payload[key]
    return payload


async def list_cursor(
    client: NeonClient,
    path: str,
    key: str,
    params: dict[str, Any],
    limit: int | None,
    cursor: str | None,
) -> dict:
    """GET a cursor-paginated Neon list endpoint and return {<key>, count, has_more, next_cursor}.

    Neon pages with an opaque cursor (not a page number): pass the previous result's
    next_cursor straight back to continue. dump_json_capped's own size-based truncation
    (applied by run_tool) is still a second, response-size-driven safety net.
    """
    query = compact(params) | {"limit": limit or DEFAULT_PAGE_SIZE}
    if cursor:
        query["cursor"] = cursor
    payload = await client.get(path, query)
    items = payload.get(key) if isinstance(payload, dict) else payload
    items = items if isinstance(items, list) else []
    pagination = payload.get("pagination") if isinstance(payload, dict) else None
    next_cursor = pagination.get("cursor") if isinstance(pagination, dict) else None
    return compact({key: items, "count": len(items), "has_more": bool(next_cursor), "next_cursor": next_cursor})


def not_confirmed(action: str) -> dict:
    return {
        "done": False,
        "action": action,
        "message": "Not done. Describe this deletion to the user and call again with confirm: true only after they approve it.",
    }


async def run_tool(
    name: str,
    client_factory: ClientFactory,
    action: Callable[[NeonClient], Awaitable[Any]],
) -> str:
    """Resolve the caller's client, run ``action``, and always return a string.

    Errors never escape as exceptions: they become the standard error envelope.
    """
    client = client_factory()
    if client is None:
        return NOT_CONFIGURED
    started = time.monotonic()
    try:
        result = await action(client)
    except NeonError as e:
        logger.info("tool=%s outcome=error status=%s ms=%d", name, e.status_code, _ms(started))
        return e.to_envelope()
    except ValueError as e:
        logger.info("tool=%s outcome=invalid_argument ms=%d", name, _ms(started))
        return error_envelope("invalid_argument", str(e), False)
    except Exception as e:  # noqa: BLE001 - tools must never raise
        logger.warning("tool=%s outcome=unexpected error=%s ms=%d", name, type(e).__name__, _ms(started))
        return error_envelope("upstream_error", f"Unexpected error: {type(e).__name__}", True)
    logger.info("tool=%s outcome=ok ms=%d", name, _ms(started))
    if result is None:
        result = {"done": True}
    return result if isinstance(result, str) else dump_json_capped(result)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
