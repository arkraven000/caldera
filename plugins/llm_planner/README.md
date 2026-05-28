# llm_planner — Anthropic-driven Caldera planner

In-server `LogicalPlanner` plugin that delegates per-tick decisions to Anthropic Claude. This is **Variation C** of the Caldera × Anthropic AI integration plan.

## Install

1. Install the plugin's runtime dependency:
   ```bash
   pip install -r plugins/llm_planner/requirements.txt
   ```
2. Export your Anthropic API key:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```
3. Enable the plugin in `conf/default.yml`:
   ```yaml
   plugins:
     - llm_planner
     - ...
   ```
4. Start Caldera as usual: `python3 server.py --insecure --build`.

## Use

Create an operation with `planner: llm`. The planner YAML at
`plugins/llm_planner/data/planners/7c2b0e10-llm-planner.yml` registers the planner
with sensible defaults:

```yaml
params:
  model: claude-sonnet-4-7
  max_calls: 30
  dry_run: true
  allowlist_tactics: [discovery, collection]
  deny_tactics: [impact]
```

Override per operation via the operation's `planner.params` field when creating it through `/api/v2/operations` or the UI.

## Safety

- **dry_run: true** (default) — chosen links are marked DISCARD; nothing executes on any agent.
- **allowlist** — applied BEFORE the prompt; the model never sees disallowed abilities.
- **max_calls** — hard cap on Anthropic API calls per operation; planner halts cleanly when reached.
- **fail-closed** — any Anthropic API error halts the planner instead of falling back to atomic.
- **audit** — every decision (and every denial) appended to `data/ai_audit/<operation_id>.jsonl`.

## Flipping to live execution

Set `dry_run: false` on the operation's planner params. The audit log records the flip, every decision before execution, and the resulting link id. Combine with a tight allowlist (`allowlist_tactics: [discovery]`) the first time you do this against a real agent.

## Cost / latency

A typical decision uses ~5–15k input tokens (mostly the candidate list + recent chain). The system prompt and candidate list are both `cache_control: ephemeral`, so subsequent ticks within the same operation get most of the prompt as cache reads. Confirm cache hits by tailing the audit JSONL — every `decision` event carries `_usage.cache_read_input_tokens`.
