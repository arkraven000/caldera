"""Tool dispatch table for the standalone Anthropic-driven agent.

Each entry maps a tool name (matching CALDERA_TOOL_SPECS in app.ai_safety.tools_schema)
to an async callable taking (client, **kwargs). The dispatcher applies the safety layer
(allowlist + audit + approval) before invoking the underlying Caldera client.
"""

from typing import Any

from app.ai_safety import AbilityAllowlist, AuditLogger
from tools.claude_agent.approval import needs_approval, prompt_operator


async def _list_abilities(client, *, tactic: str = None, technique_id: str = None, **_):
    rows = await client.list_abilities(tactic=tactic, technique_id=technique_id)
    return [{'ability_id': r.get('ability_id'), 'name': r.get('name'), 'tactic': r.get('tactic'),
             'technique_id': r.get('technique_id'),
             'description': (r.get('description') or '')[:200]} for r in rows[:200]]


async def _get_operation(client, *, operation_id: str, **_):
    op = await client.get_operation(operation_id) or {}
    return {
        'id': op.get('id'),
        'name': op.get('name'),
        'state': op.get('state'),
        'planner': (op.get('planner') or {}).get('name'),
        'adversary': (op.get('adversary') or {}).get('name'),
        'agent_paws': [a.get('paw') for a in (op.get('host_group') or op.get('agents') or [])],
        'chain_count': len(op.get('chain') or []),
        'last_links': [{'ability_id': (l.get('ability') or {}).get('ability_id'),
                        'status': l.get('status'), 'paw': l.get('paw')}
                       for l in (op.get('chain') or [])[-10:]],
    }


async def _list_agents(client, **_):
    rows = await client.list_agents()
    return [{'paw': r.get('paw'), 'host': r.get('host'), 'platform': r.get('platform'),
             'username': r.get('username'), 'privilege': r.get('privilege')} for r in rows]


async def _get_facts(client, *, operation_id: str, **_):
    facts = await client.get_facts(operation_id)
    return [{'trait': f.get('trait'), 'value': f.get('value'), 'source': f.get('source')} for f in facts[:200]]


async def _add_fact(client, *, operation_id: str, trait: str, value: str, **_):
    return await client.add_fact(operation_id, trait, value)


async def _propose_link(client, *, operation_id: str, ability_id: str, paw: str, **_):
    return await client.propose_link(operation_id, ability_id, paw)


async def _list_potential_links(client, *, operation_id: str, paw: str = None, **_):
    return await client.list_potential_links(operation_id, paw=paw)


async def _execute_link(client, *, operation_id: str, link_payload: dict, mode: str = 'interactive', **_):
    if mode == 'dry-run':
        ability_id = (link_payload or {}).get('ability', {}).get('ability_id')
        return {'status': 'dry-run',
                'message': 'execute_link suppressed; would have executed',
                'ability_id': ability_id,
                'paw': (link_payload or {}).get('paw')}
    return await client.execute_link(operation_id, link_payload)


async def _wait_for_link(client, *, operation_id: str, link_id: str, timeout_seconds: int = 120, **_):
    return await client.wait_for_link(operation_id, link_id, timeout_seconds=timeout_seconds)


async def _pause_operation(client, *, operation_id: str, mode: str = 'interactive', **_):
    if mode == 'dry-run':
        return {'status': 'dry-run', 'message': 'pause_operation suppressed'}
    return await client.pause_operation(operation_id)


async def _resume_operation(client, *, operation_id: str, mode: str = 'interactive', **_):
    if mode == 'dry-run':
        return {'status': 'dry-run', 'message': 'resume_operation suppressed'}
    return await client.resume_operation(operation_id)


async def _summarize(client, *, operation_id: str, audience: str = 'operator', **_):
    op = await client.get_operation(operation_id) or {}
    chain = op.get('chain') or []
    facts = op.get('facts') or []
    return {
        'audience': audience,
        'operation': op.get('name'),
        'state': op.get('state'),
        'links_executed': len(chain),
        'facts_collected': len(facts),
        'last_tactics': sorted({(l.get('ability') or {}).get('tactic') for l in chain if l.get('ability')} - {None}),
    }


async def _stop_operation(client, *, reason: str, **_):
    return {'status': 'stop', 'reason': reason}


DISPATCH = {
    'list_abilities': _list_abilities,
    'get_operation': _get_operation,
    'list_agents': _list_agents,
    'get_facts': _get_facts,
    'add_fact': _add_fact,
    'propose_link': _propose_link,
    'list_potential_links': _list_potential_links,
    'execute_link': _execute_link,
    'wait_for_link': _wait_for_link,
    'pause_operation': _pause_operation,
    'resume_operation': _resume_operation,
    'summarize': _summarize,
    'stop_operation': _stop_operation,
}


async def dispatch(tool_name: str, tool_input: dict, *, client, allowlist: AbilityAllowlist,
                   audit: AuditLogger, mode: str) -> Any:
    """Apply safety + audit + approval, then invoke the underlying tool."""
    if tool_name not in DISPATCH:
        return {'error': f'unknown tool {tool_name}'}

    # Allowlist check for ability-targeting tools.
    if tool_name in ('propose_link', 'execute_link'):
        ability_id = tool_input.get('ability_id')
        if not ability_id and tool_name == 'execute_link':
            ability_id = (tool_input.get('link_payload') or {}).get('ability', {}).get('ability_id')
        # We only have the ability_id here; the allowlist can still match on id.
        permitted, reason = allowlist.permits({'ability_id': ability_id, 'tactic': None, 'technique_id': None})
        if allowlist.is_restrictive and not permitted:
            await audit.record('tool_denied', {'tool': tool_name, 'input': tool_input, 'reason': reason})
            return {'error': f'denied by allowlist: {reason}'}

    # Operator approval gate.
    if needs_approval(tool_name, mode):
        approved, edited, msg = prompt_operator(tool_name, tool_input)
        if not approved:
            await audit.record('tool_declined', {'tool': tool_name, 'input': tool_input, 'message': msg})
            return {'error': f'operator declined: {msg}'}
        tool_input = edited or tool_input
        await audit.record('tool_approved', {'tool': tool_name, 'input': tool_input, 'message': msg})

    await audit.record('tool_call', {'tool': tool_name, 'input': tool_input, 'mode': mode})
    try:
        result = await DISPATCH[tool_name](client, mode=mode, **tool_input)
    except Exception as exc:
        await audit.record('tool_error', {'tool': tool_name, 'error': str(exc)})
        return {'error': str(exc)}
    await audit.record('tool_result', {'tool': tool_name, 'result_summary': _summarize_result(result)})
    return result


def _summarize_result(result: Any) -> Any:
    """Trim large results in the audit log; full result still goes back to the model."""
    if isinstance(result, list):
        return {'type': 'list', 'count': len(result), 'sample': result[:3]}
    if isinstance(result, dict):
        keys = list(result.keys())
        return {'type': 'dict', 'keys': keys[:20]}
    return {'type': type(result).__name__}
