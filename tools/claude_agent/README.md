# claude_agent — Anthropic-driven external client for Caldera

A standalone Python module that uses the Anthropic Python SDK's tool-use loop to drive a remote MITRE Caldera server through its REST v2 API. **No server-side changes required.**

This is **Variation B** of the Caldera × Anthropic AI integration plan. It is the safest of the three variations to ship first because it has zero server-side footprint — it just calls REST.

## Install

```bash
pip install -r tools/claude_agent/requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
export CALDERA_URL=http://127.0.0.1:8888
export CALDERA_API_KEY=ADMIN123   # the api_key_red value from conf/default.yml
```

## Run (dry-run)

```bash
python -m tools.claude_agent \
  --operation <operation-id> \
  --goal "Enumerate users and find sensitive files on connected hosts" \
  --mode dry-run
```

In dry-run, no mutating tool call is sent to Caldera — `execute_link`, `add_fact`, `pause_operation`, and `resume_operation` are intercepted client-side and return a "would have executed" placeholder.

## Modes

- `dry-run` (default) — model reasons and proposes, nothing executes.
- `interactive` — model proposes, operator approves each mutating call with `y`/`N`/`e` (edit JSON input).
- `auto` — model runs unattended; requires `--allowlist` with at least one positive constraint.

## Allowlist

```bash
--allowlist 'tactics=discovery,collection;deny_tactics=impact;deny_ability_ids=abc123'
```

Mutating tools targeting an ability outside the allowlist are denied before they hit the API. Denies always win.

## Audit

Every model decision, tool call, approval, denial, and result summary is appended as JSONL to `~/.caldera_ai/audit/<operation_id>.jsonl` (override with `--audit-dir`).

## Safety notes

- The standalone client should NOT be run against an operation that has an active server-side planner (e.g. `atomic`, or the `llm_planner` plugin). Call `pause_operation` first or set the operation's planner to `manual`.
- Prefer red-team API key (`api_key_red`) — the blue key has fewer write permissions.
- The model is given the ability catalog as a prompt-cached block; the first call writes the cache, every subsequent call reads it. Check the printed token summary for `cache_read` > 0 to confirm caching is active.
