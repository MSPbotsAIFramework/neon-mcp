# Neon MCP Server

An [MCP](https://modelcontextprotocol.io) server for the [Neon](https://neon.tech) API (v2),
the serverless Postgres platform. It lets an AI agent manage one Neon account's
**infrastructure** — projects, instant copy-on-write branches, compute endpoints, databases and
roles — and hand back a ready-to-use Postgres connection string. It does not run SQL against the
data a branch holds: that is a different protocol (the Postgres wire protocol, not Neon's REST
API) and a different security posture, out of scope for this connector.

- Transport: MCP Streamable HTTP at `POST /mcp`, health probe at `GET /health`
- Stateless and multi-tenant: credentials arrive on every request as an HTTP header and are
  never stored; every tool is listed from the first `tools/list`
- Python 3.12, [uv](https://docs.astral.sh/uv/), FastMCP, httpx
- License: Apache-2.0, Copyright 2026 MSPbots.ai

<div align="center">

## MSPbots Connector

**The MCP Gateway built for MSPs: visible, controlled, and your data stays where it belongs.**

[**Get started at connect.mspbots.ai →**](https://connect.mspbots.ai)

</div>

---

MSPbots Connector gives your AI clients one MCP URL to reach your entire MSP stack (RMM, PSA, documentation, security, finance), and gives you control over who can call which tool and a record of everything that was called.

**Hosted service: [connect.mspbots.ai](https://connect.mspbots.ai)** · Free to use.

### Why Connector

![MSPbots Connector](https://stgoss.mspbots.ai/files/mcp/mspbots-mcp.png)

| | |
|---|---|
| **Visible** | Every tool call is logged: who, which vendor, when. Usage dashboard, CSV export, SIEM streaming. |
| **Controlled** | Role-based, per-tool allowlist. Deny by default. |
| **Protected** | Credentials encrypted per record. AI clients never see your vendor passwords or tokens. |
| **MSP-native** | Built for the MSP stack only: RMM, PSA, documentation, security, finance. |

### Quick start

1. **Sign up** at [connect.mspbots.ai](https://connect.mspbots.ai).
2. **Connect your vendors.** Pick from 150+ connectors and authorize each one on the vendor's own page, or bring your own API keys. No extra vendor accounts needed.
3. **Set access.** Create roles and decide which tools each role may call. Nothing is allowed until you allow it.
4. **Add your MCP URL to your AI client.** Copy the URL from your Connector dashboard into Claude, ChatGPT, Cursor, VS Code, Gemini, Codex, or any MCP-capable client.
5. **Ask your AI to do real work**, and watch every call appear in the audit log.

### Features

**Unified gateway**
- One MCP URL for all your AI clients
- 150+ connectors across the MSP stack
- Custom MCP servers supported, free
- Authorization happens on each vendor's own page; the AI never sees passwords or tokens
- Bring your own credentials: use the vendor API keys you already have
- Multiple accounts per app; connect once, reuse across AI clients
- Tool search: finds the right action for the task
- One sign-in; vendor credentials are injected behind the scenes and OAuth tokens refresh automatically

**Visibility**
- Audit log for every tool call (who, which vendor, when)
- Usage dashboard: call volume, top vendors, error rate, per-user activity
- Export audit logs to CSV, or stream to Loki, Graylog, or LogScale (SIEM)
- Optional recording of tool arguments and result summaries (off by default, enabled per organization)

**Control**
- Per-role, per-tool allowlist, deny by default
- owner / admin / member roles
- SCIM provisioning with Entra ID, Okta, JumpCloud, and Google Workspace

**Security**
- Credentials encrypted one record at a time (AES-256-GCM, per-record key)
- AI clients authenticate with OAuth 2.1 + PKCE
- Vendor responses are scanned for prompt-injection patterns and returned as structured data. This is one layer of defense, not a guarantee against every attack.
- Static egress IP for customer firewall and API allowlisting

### Pricing

**Free.**

Links: [connect.mspbots.ai](https://connect.mspbots.ai) · [mspbots.ai](https://mspbots.ai)

---

## Authentication headers

| Header | Required | Type | Default | Allowed values | Description | Example |
|---|---|---|---|---|---|---|
| `X-Neon-API-Key` | Yes | string | none | - | Neon personal or organization API key | `napi_xxx` |

Where to get it: Neon Console → Account settings → API keys → create a key. Neon has exactly one
API host (`console.neon.tech`), so there is no base-URL header to configure.

How the key is sent to Neon: every call goes to `https://console.neon.tech/api/v2/...` with the
key as `Authorization: Bearer <key>`.

A request to `/mcp` without the header gets HTTP 401 naming it.

## Tools

All tools return a JSON string. List tools take `limit` (default 10, max 400, matching Neon's own
API defaults) and an opaque `cursor`; the result includes `has_more` and `next_cursor` — pass
`next_cursor` back to continue. **write** marks tools that change infrastructure; **confirm**
marks the one delete tool, which also needs `confirm: true`.

| Area | Tools |
|---|---|
| Projects | `neon_list_projects` (search), `neon_get_project` (**project_id**) |
| Branches | `neon_list_branches` (**project_id**), `neon_get_branch` (**project_id**, **branch_id**); **write**: `neon_create_branch` (**project_id**, branch_name, parent_id); **confirm**: `neon_delete_branch` (**project_id**, **branch_id**) |
| Compute endpoints | `neon_list_endpoints` (**project_id**), `neon_get_endpoint` (**project_id**, **endpoint_id**) |
| Databases | `neon_list_databases` (**project_id**, **branch_id**); **write**: `neon_create_database` (**project_id**, **branch_id**, **database_name**, **owner_name**) |
| Roles | `neon_list_roles` (**project_id**, **branch_id**); **write**: `neon_create_role` (**project_id**, **branch_id**, **role_name**) |
| Connection | `neon_get_connection_uri` (**project_id**, **database_name**, **role_name**, branch_id, pooled) |
| Operations | `neon_list_operations` (**project_id**), `neon_get_operation` (**project_id**, **operation_id**) |

Errors come back as a JSON envelope instead of an exception:

```json
{"error": {"code": "not_found", "message": "Neon returned HTTP 404 for projects/p1/branches/br-x: branch not found", "retryable": false}}
```

`code` is one of `not_configured`, `unauthorized`, `not_found`, `invalid_argument`,
`rate_limited`, `upstream_error`. Reads are retried with backoff on 429 and 5xx/network errors;
writes only on 429, so a write is never silently run twice.

## Run locally

```bash
uv sync
uv run python -m neon_mcp          # listens on 0.0.0.0:8080
```

or with Docker:

```bash
docker build --platform linux/amd64 -t neon-mcp:dev .
docker run --rm -p 8080:8080 neon-mcp:dev
```

Configuration (environment variables, all optional): `MCP_HTTP_HOST` (default `0.0.0.0`),
`MCP_HTTP_PORT` (default `8080`), `LOG_LEVEL` (default `INFO`). Credentials are never read
from the environment.

## Testing example

```bash
# list tools
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Neon-API-Key: your-neon-api-key" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# list branches of one project
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Neon-API-Key: your-neon-api-key" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"neon_list_branches","arguments":{"project_id":"your-project-id"}}}'
```

Unit tests (no network access needed):

```bash
uv run pytest
```

## Scope (v1)

**In scope**: list/get projects, branches, compute endpoints, databases, roles and operations;
create and delete branches (delete needs `confirm: true`); create databases and roles; get a
connection URI.

**Out of scope for this version** — see `docs/tickets/PRD-21329.md` (Product design → Non-goals)
for the full reasoning:

- Running SQL against the data a branch holds (a different protocol and risk profile; the
  connection URI this connector returns is for a separate Postgres client to use).
- Organizations, Snapshots, Neon Auth, serverless Functions, Realtime subscriptions, VPC
  endpoints, consumption/billing history, project-level API key management.
- Updating/suspending compute endpoints, renaming projects/branches, deleting databases, roles
  or projects, rotating role passwords.

## Delivery notes

- **`neon_create_role`'s response may include a one-time generated password.** It is returned
  directly in the tool result and never stored or logged (the connector's logging policy is
  method/path/status/ms only, never response bodies or the API key).
- **`neon_delete_branch` needs `confirm: true`** — it is the only destructive tool in v1; without
  it, the tool returns a `"done": false` result and never calls Neon.
- **Pagination is cursor-based**, not page-number based like some other connectors in this org:
  pass `next_cursor` back as `cursor` to continue.
- **Error body schema**: Neon's documented error schema (`$ref: GeneralError`) did not resolve to
  concrete fields during design, so errors are classified by HTTP status first and a message is
  extracted best-effort from `message`/`error` fields second, the same defensive pattern used
  elsewhere in this org.

## License

Apache License 2.0 - see [LICENSE](LICENSE) and [NOTICE](NOTICE).
