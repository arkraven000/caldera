# mcp_server — MCP bridge for Claude Code

Exposes Caldera as a Model Context Protocol server. This is **Variation A** of the Caldera × Anthropic AI integration plan and is intended for **local** Claude Code instances driving an operator's lab.

## Install

```bash
pip install -r plugins/mcp_server/requirements.txt
```

Add `mcp_server` to the `plugins:` list in `conf/default.yml`, then restart Caldera.

## Transports

### stdio (recommended for local Claude Code)

Start Caldera with `MCP_STDIO=1`:

```bash
MCP_STDIO=1 python3 server.py --insecure --build
```

Then register the server in Claude Code:

```bash
claude mcp add caldera \
  --command python3 \
  --args server.py --args --insecure
```

### SSE (remote / multi-client)

Routes are mounted at:
- `GET /plugin/mcp_server/sse` — event stream
- `POST /plugin/mcp_server/messages` — JSON-RPC

By default the SSE handler returns a 501 because completing the aiohttp ↔ MCP SDK bridge requires hand-wiring that depends on the SDK version you pin. Edit `transports.py` to plug in `SseServerTransport.connect_sse(...)` per the MCP SDK docs once you've chosen a version.

**Security**: when binding non-loopback, set `MCP_BEARER_TOKEN=...` so the SSE routes require an `Authorization: Bearer ...` header. The plugin will 401 otherwise.

## Tools exposed

Read-only:
- `list_operations`
- `get_operation(operation_id)`
- `list_abilities(tactic?, technique_id?)`
- `list_agents(operation_id?)`
- `get_facts(operation_id)`
- `summarize_operation(operation_id)`

Mutating (gated):
- `propose_next_link(operation_id, ability_id, paw)` — runs `planning_svc.get_links`, applies the allowlist, mints a single-use 60s approval token.
- `approve_and_execute_link(operation_id, link_id, approval_token)` — verifies the token, executes the link, blocks until completion.

## Safety

- **AbilityAllowlist** filters all proposed links. Default: tactics `[discovery, collection]`, deny `[impact]`. Override via `MCP_ALLOWLIST_TACTICS` / `MCP_DENY_TACTICS` env vars.
- **Single-use approval tokens** (60s TTL) prevent stale or replayed approvals.
- **AuditLogger** writes every propose / approve / deny / execute event to `data/ai_audit/<operation_id>.jsonl`.
- **Loopback-only by default**. Add a bearer token before binding to a non-localhost interface.

## Critical risk

MCP gives the client persistent in-process access to `services` (data_svc, planning_svc, knowledge_svc). A misconfigured allowlist combined with an exposed SSE endpoint is effectively RCE on every connected sandcat agent. Treat the MCP endpoint exactly like the Caldera API key: do not expose it beyond a trust boundary you control.
