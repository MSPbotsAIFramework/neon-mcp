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
"""Request shapes, retries and error-envelope mapping against a mocked Neon API (TC17-TC19)."""

import httpx
import pytest

from neon_mcp import api_client
from neon_mcp.api_client import NeonClient, NeonCredentials, NeonError

CREDS = NeonCredentials("key-123")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(api_client.asyncio, "sleep", instant)


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


def _client(recorder: Recorder) -> NeonClient:
    return NeonClient(CREDS, httpx.AsyncClient(transport=httpx.MockTransport(recorder)))


async def test_auth_header_is_bearer_key_and_bool_params_lowercased():
    rec = Recorder({"projects/p1/connection_uri": {"uri": "x"}})
    await _client(rec).get("projects/p1/connection_uri", {"pooled": True})
    request = rec.requests[0]
    assert request.headers["Authorization"] == "Bearer key-123"
    assert request.url.params["pooled"] == "true"


# ---- TC17 (AC14): 401/403 -> unauthorized ----------------------------------


@pytest.mark.parametrize("status", [401, 403])
async def test_401_403_mapped_to_unauthorized_envelope(status):
    rec = Recorder({"GET projects/p1": lambda r: httpx.Response(status, json={"message": "bad key"})})
    with pytest.raises(NeonError) as excinfo:
        await _client(rec).get("projects/p1")
    code, retryable = api_client.classify_status(excinfo.value.status_code)
    assert code == "unauthorized" and retryable is False
    assert "bad key" in excinfo.value.message


# ---- TC18 (AC14): 404 -> not_found -----------------------------------------


async def test_404_mapped_to_not_found_envelope():
    rec = Recorder({"GET projects/missing": lambda r: httpx.Response(404, json={"message": "project not found"})})
    with pytest.raises(NeonError) as excinfo:
        await _client(rec).get("projects/missing")
    code, retryable = api_client.classify_status(excinfo.value.status_code)
    assert code == "not_found" and retryable is False
    assert "project not found" in excinfo.value.message


# ---- TC19 (AC14): 429 retried with backoff on reads, then rate_limited -----


async def test_429_retried_then_rate_limited_envelope():
    rec = Recorder(
        {"GET projects": lambda r: httpx.Response(429, headers={"Retry-After": "1"}, json={"message": "slow down"})}
    )
    with pytest.raises(NeonError) as excinfo:
        await _client(rec).get("projects")
    assert len(rec.calls("projects", "GET")) == 3  # 1 initial + 2 retries (_MAX_RETRIES)
    code, retryable = api_client.classify_status(excinfo.value.status_code)
    assert code == "rate_limited" and retryable is True


async def test_get_retries_5xx_but_writes_do_not():
    replies = iter([httpx.Response(502), httpx.Response(200, json={"projects": []})])
    rec = Recorder(
        {"GET projects": lambda r: next(replies), "POST projects/p1/branches": lambda r: httpx.Response(500, json={})}
    )
    client = _client(rec)
    await client.get("projects")
    with pytest.raises(NeonError):
        await client.post("projects/p1/branches", {})
    assert len(rec.calls("projects", "GET")) == 2 and len(rec.calls("projects/p1/branches", "POST")) == 1


async def test_html_error_pages_are_not_echoed():
    rec = Recorder({"GET projects/p1": lambda r: httpx.Response(502, text="<html><body>Bad Gateway</body></html>")})
    with pytest.raises(NeonError) as excinfo:
        await _client(rec).get("projects/p1")
    assert excinfo.value.message == "Neon returned HTTP 502 for projects/p1"


async def test_network_error_never_retried_past_the_call_budget():
    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    rec = Recorder({"GET projects": boom})
    with pytest.raises(NeonError) as excinfo:
        await _client(rec).get("projects")
    assert excinfo.value.status_code == 0
    assert len(rec.calls("projects", "GET")) == 3


# ---- multi-tenant isolation (AC15): the shared client never carries a per-request key -----


async def test_shared_http_client_never_stores_or_sends_cookies():
    client = api_client._get_shared_http_client()
    assert isinstance(client.cookies.jar._policy, api_client._RejectAllCookies)
