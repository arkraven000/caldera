"""Anthropic tool-use loop driving the Caldera client."""

import json
import logging

from app.ai_safety import (
    AbilityAllowlist,
    AuditLogger,
    CALDERA_TOOL_SPECS,
    MODEL_STEP,
    DEFAULT_MAX_TOKENS,
    get_async_client,
)
from app.ai_safety.anthropic_client import cache_block
from tools.claude_agent.prompts import PLANNER_SYSTEM, operator_goal_prompt
from tools.claude_agent.tools import dispatch


log = logging.getLogger(__name__)


async def run(*, caldera_client, anthropic_client=None, operation_id: str, goal: str,
              mode: str = 'dry-run', model: str = MODEL_STEP, max_steps: int = 20,
              max_tokens: int = DEFAULT_MAX_TOKENS, allowlist: AbilityAllowlist = None,
              audit_dir: str = None) -> dict:
    """Run a single agent session against the given operation.

    Returns a dict summarizing the session: steps taken, terminal reason, total token usage.
    """
    if anthropic_client is None:
        anthropic_client = get_async_client()
    allowlist = allowlist or AbilityAllowlist()
    audit = AuditLogger(operation_id, root=audit_dir)
    await audit.record('session_start', {'goal': goal, 'mode': mode, 'model': model, 'max_steps': max_steps})

    catalog_rows = await caldera_client.list_abilities()
    catalog_text = json.dumps([{
        'ability_id': r.get('ability_id'),
        'name': r.get('name'),
        'tactic': r.get('tactic'),
        'technique_id': r.get('technique_id'),
        'description': (r.get('description') or '')[:200],
    } for r in catalog_rows[:500]])

    messages = [{
        'role': 'user',
        'content': [
            cache_block(f'CALDERA ABILITY CATALOG (cached):\n{catalog_text}'),
            {'type': 'text', 'text': operator_goal_prompt(operation_id, goal, mode)},
        ],
    }]
    system = [cache_block(PLANNER_SYSTEM)]

    total_in = total_out = 0
    cache_in = 0
    cache_read = 0
    stop_reason = 'max_steps_reached'

    for step in range(max_steps):
        resp = await anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=CALDERA_TOOL_SPECS,
            messages=messages,
        )
        usage = getattr(resp, 'usage', None)
        if usage:
            total_in += getattr(usage, 'input_tokens', 0) or 0
            total_out += getattr(usage, 'output_tokens', 0) or 0
            cache_in += getattr(usage, 'cache_creation_input_tokens', 0) or 0
            cache_read += getattr(usage, 'cache_read_input_tokens', 0) or 0

        messages.append({'role': 'assistant', 'content': resp.content})

        tool_uses = [b for b in resp.content if getattr(b, 'type', None) == 'tool_use']
        if not tool_uses:
            stop_reason = f'model_stop:{getattr(resp, "stop_reason", "unknown")}'
            break

        tool_results = []
        stop_signal = False
        for block in tool_uses:
            result = await dispatch(
                block.name, dict(block.input or {}),
                client=caldera_client, allowlist=allowlist, audit=audit, mode=mode,
            )
            tool_results.append({
                'type': 'tool_result',
                'tool_use_id': block.id,
                'content': json.dumps(result, default=str)[:8000],
            })
            if block.name == 'stop_operation':
                stop_signal = True
                stop_reason = f'stop_operation: {(result or {}).get("reason", "no reason")}'

        messages.append({'role': 'user', 'content': tool_results})
        if stop_signal:
            break

    summary = {
        'operation_id': operation_id,
        'steps': step + 1,
        'stop_reason': stop_reason,
        'tokens': {
            'input': total_in,
            'output': total_out,
            'cache_created': cache_in,
            'cache_read': cache_read,
        },
    }
    await audit.record('session_end', summary)
    return summary
