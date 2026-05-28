# app/ai_safety — shared safety infrastructure for Caldera AI integrations

This package is the shared foundation under all three Caldera × Anthropic AI integration variations:

| Variation | Where | Consumer |
|---|---|---|
| **A — MCP server** | `plugins/mcp_server/` | Local Claude Code (operator's laptop) |
| **B — Standalone client** | `tools/claude_agent/` | Hosted Claude agents (Claude on the web, automation) |
| **C — In-server LLM planner** | `plugins/llm_planner/` | Caldera itself, autonomous |

Each variation imports the same primitives from this package, so a policy change (e.g. adding `impact` to the deny list) is a one-place edit.

## Modules

- `allowlist.py` — `AbilityAllowlist(ability_ids, tactics, technique_ids, deny_*)`. Filter abilities by id / tactic / technique with explicit denies. Deny always wins; empty allow means permissive.
- `audit.py` — `AuditLogger(operation_id, root)`. Appends JSONL to `data/ai_audit/<op_id>.jsonl`. Best-effort: never raises into the planner loop.
- `scoping.py` — `TargetScope(paws, cidrs)`. Restrict agents by paw and target IPs by CIDR.
- `catalog.py` — `build_ability_catalog(data_svc)` and `compact_*` projections used to fit Caldera objects into prompt budgets.
- `anthropic_client.py` — `get_async_client()` factory + `cache_block(text)` helper for prompt-cached content. Pinned model ids: `MODEL_PLAN=claude-opus-4-7`, `MODEL_STEP=claude-sonnet-4-7`.
- `tools_schema.py` — JSONSchema tool definitions: `CHOOSE_NEXT_LINK_TOOL` (used by the in-server planner) and `CALDERA_TOOL_SPECS` (used by the standalone client + MCP server).

## Safety posture

Defaults across all three variations:

- **dry-run by default** — proposed links are marked DISCARD; no commands actually run on agents.
- **allowlist required for auto mode** — autonomous execution refuses to start without at least one positive allowlist constraint.
- **single-use approval tokens** (MCP) — 60-second TTL, bound to (operation, link).
- **operator approval prompts** (standalone) — y/N/e gate on every mutating call in `--mode interactive`.
- **audit JSONL** — every decision, denial, approval, and tool result is logged.
- **fail-closed** — Anthropic API errors or missing keys halt the planner cleanly rather than falling back to atomic execution.

## Configuration

The shared sample lives at `app/ai_safety/ai.example.yml`. Copy it to `conf/ai.yml` (gitignored, like the rest of `conf/*.yml`) and edit for your environment. Per-variation overrides live in each plugin's `conf/default.yml` or the standalone client's CLI flags.

Required env vars:
- `ANTHROPIC_API_KEY` — for any variation that calls Claude server-side.
- `CALDERA_URL`, `CALDERA_API_KEY` — for the standalone client only.
- `MCP_STDIO=1`, `MCP_BEARER_TOKEN=...` — for the MCP plugin transports.
