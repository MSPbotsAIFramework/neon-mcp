# PRD-21329 · Code review

## Round 1 · 2026-11-05 · reviewed dev/PRD-21329 @ 7e86c56 (base main @ 2ee9ed0)

Status: frozen @ 7e86c56

Verdict: approved

### Scope

`git diff 2ee9ed0...7e86c56` in `MSPbotsAIFramework/neon-mcp` (32 files, +3742/-2): full repo scaffold
(`pyproject.toml`, `Dockerfile`, `docker-compose.yml`, licensing files), `src/neon_mcp/` (config,
API client, FastMCP server + credential middleware, 15 tools across 7 modules), `tests/` (4 files,
42 cases), `README.md`, and `docs/tickets/PRD-21329.{md,ac.json}`. This is a brand-new repo (main
was a two-line README before this branch); every line in the diff is this ticket's work.

### Findings

1. [suggestion] `src/neon_mcp/api_client.py:61-65` — `_get_shared_http_client()` lazily creates the
   module-level `httpx.AsyncClient` singleton with a plain `if _shared_http_client is None` check
   and no lock. Two concurrent requests hitting a cold process at the same time could each pass the
   check and construct their own client; whichever assignment runs last wins and the other instance
   is leaked (never closed) rather than reused. This is not a correctness or multi-tenant-isolation
   problem — both instances still reject cookies (`_RejectAllCookies`) and hold no credentials, so
   no data can cross tenants — just a minor resource-cleanliness gap. The pattern is reused verbatim
   from `hudu-mcp` (per the tech design's Reuse & cleanup section), so it predates this ticket;
   worth fixing in `hudu-mcp` itself if that repo is revisited, not a reason to hold this one.

No must-fix findings.

### Checklist cross-check (SOP §14, spot-checked against the diff, not re-run)

- Streamable HTTP at `/mcp`, local-only `/health` → `{"status":"ok"}`: `src/neon_mcp/__main__.py:47-62`.
- Default `0.0.0.0:8080`, unknown env vars ignored (`extra="ignore"`): `src/neon_mcp/config.py:26-32`.
- Stateless (`stateless_http=True`), no persisted session state: `src/neon_mcp/server.py:111-120`.
- Credentials from `X-Neon-API-Key` header only, never from env/config; `NeonCredentials.__repr__`
  redacts the key: `src/neon_mcp/api_client.py:104-109`; header name matches README verbatim.
- Missing header → 401 naming the header before any upstream call:
  `src/neon_mcp/server.py:83-99`, exercised in `tests/test_middleware.py`.
- Per-request isolation via `contextvars`, reset in `finally`: `src/neon_mcp/server.py:100-108`,
  concurrency exercised in `tests/test_middleware.py::test_concurrent_requests_do_not_share_credentials`.
- DNS-rebinding protection disabled (service sits behind the gateway): `src/neon_mcp/server.py:118`.
- MCP app lifespan wired to the outer Starlette app (comment explains why): `src/neon_mcp/__main__.py:54-62`.
- Multi-stage Dockerfile, non-root `app` user, `curl` installed for `HEALTHCHECK`, `EXPOSE 8080`,
  default `MCP_HTTP_PORT`/`MCP_HTTP_HOST` env, `uv.lock` committed: `Dockerfile`.
- README has the credential header table before the MSPbots Connector section — actually the
  Connector section comes first in this README (`README.md:16-86`) per the SOP's own ordering
  (§0.5: Connector section before the header table), confirmed identical to
  `reference/readme-connector-section.md` (`diff` run during this review, 0 lines).
- No Chinese anywhere in the tree (`grep -rnP '[\x{4e00}-\x{9fff}]'` run during this review, no output).
- Structured error envelope (`code`/`message`/`retryable`), fixed vocabulary, no raw exceptions
  escape a tool: `src/neon_mcp/tools/_common.py:96-123`, `src/neon_mcp/api_client.py:93-101,197-214`.
- Outbound timeouts (`connect=5s read=30s write=10s pool=5s`), bounded retry/backoff respecting
  `Retry-After`, 100s call budget under the gateway's 120s tool-call timeout, writes retried only on
  429 (never silently re-run): `src/neon_mcp/api_client.py:34-38,132-177,186-194`, exercised in
  `tests/test_api_client.py`.

### Design conformance

- All 15 tools match the tech design's Change list and endpoint map exactly (names, paths, required
  args) — cross-checked `tests/test_tools.py:34-50`'s `EXPECTED_TOOLS` snapshot against the design's
  Data & API contract table; `neon_delete_branch` is the only destructive tool and requires
  `confirm: true` before calling Neon (AC4/AC5, `src/neon_mcp/tools/branches.py:77-89`,
  `tests/test_tools.py` TC5/TC6).
- `neon_create_role`'s possible one-time password is passed through in the result and never logged
  (AC10): `tests/test_tools.py::test_create_role_password_not_logged` asserts it is absent from
  `caplog`.
- Non-goals honored: no SQL-execution tool, no endpoint suspend/resume, no rename/delete beyond the
  one scoped `neon_delete_branch`, no Organizations/Snapshots/Functions/Realtime/Neon Auth tools.
- Test-case ledger (`docs/tickets/PRD-21329.ac.json`): 20/20 automated cases (TC1-TC20) recorded
  `pass`; TC21-TC23 recorded `untested` with "needs a real Neon account" — matches the SOP's "no test
  account is not a blocker" and the design's Risks & dependencies section. No case was altered to
  fit the implementation.
- Self-test section in `docs/tickets/PRD-21329.md` gives exact commands and output for each gate
  (`uv sync`, `uv run pytest -v` → 42 passed, the Chinese-text grep, the README-section diff, a
  `gitleaks` run with both findings explained as placeholder strings, and a live smoke test with the
  actual `/health`/401/`tools/list` responses) — detailed enough to audit without re-running; this
  review re-ran only the Chinese-text grep and the README-connector-section diff (both independently
  confirmed clean/identical) and did not have `uv` available in this environment to re-run the test
  suite itself (see Verification note).

### Verification note

This environment does not have `uv` installed (`mbp.py doctor` reports it `MISSING`), so this review
could not independently re-run `uv run pytest`. Per `legs/review.md` R3, review does not re-run test
suites as a matter of course; it reads the diff and the self-test evidence. The self-test's reported
numbers (42 passed, specific tool/field names, specific HTTP status codes) are concrete and
consistent with the diff's own test files (`tests/test_tools.py` registers exactly the TC1-TC20
assertions described), so they are accepted as reported. Commands independently re-run during this
review: the Chinese-text grep and the README-connector-section `diff`, both clean, both reported
above.

### Fixes

N/A — no must-fix findings, no rework round.
