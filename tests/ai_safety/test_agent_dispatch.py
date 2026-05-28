"""Tests for the safety + audit + approval wiring in tools/claude_agent/tools.py.

These tests verify that the dispatcher applies the allowlist and audit log around
every tool call, regardless of which underlying tool runs.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.ai_safety import AbilityAllowlist, AuditLogger
from tools.claude_agent import tools as agent_tools


@pytest.mark.asyncio
async def test_dispatch_denies_propose_link_outside_allowlist(tmp_path):
    client = MagicMock()
    client.propose_link = AsyncMock(return_value={'ability': {'ability_id': 'x'}})
    audit = AuditLogger('op-tst', root=tmp_path)
    allowlist = AbilityAllowlist(ability_ids=['allowed-id'])

    result = await agent_tools.dispatch(
        'propose_link', {'operation_id': 'op1', 'ability_id': 'denied-id', 'paw': 'p1'},
        client=client, allowlist=allowlist, audit=audit, mode='auto',
    )

    assert 'error' in result
    assert 'denied by allowlist' in result['error']
    client.propose_link.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_calls_underlying_tool_when_allowed(tmp_path):
    client = MagicMock()
    client.list_abilities = AsyncMock(return_value=[{'ability_id': 'a1', 'name': 'n', 'tactic': 't',
                                                     'technique_id': 'T1', 'description': 'd'}])
    audit = AuditLogger('op-tst', root=tmp_path)

    result = await agent_tools.dispatch(
        'list_abilities', {'tactic': 'discovery'},
        client=client, allowlist=AbilityAllowlist(), audit=audit, mode='auto',
    )

    client.list_abilities.assert_awaited_once()
    assert isinstance(result, list)
    assert result[0]['ability_id'] == 'a1'


@pytest.mark.asyncio
async def test_dispatch_dry_run_suppresses_execute_link(tmp_path):
    client = MagicMock()
    client.execute_link = AsyncMock()
    audit = AuditLogger('op-tst', root=tmp_path)
    payload = {'ability': {'ability_id': 'a1'}, 'paw': 'p1',
               'executor': {'name': 'sh', 'command': 'ls'}}

    result = await agent_tools.dispatch(
        'execute_link', {'operation_id': 'op1', 'link_payload': payload},
        client=client, allowlist=AbilityAllowlist(), audit=audit, mode='dry-run',
    )

    assert result['status'] == 'dry-run'
    client.execute_link.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_records_to_audit_log(tmp_path):
    client = MagicMock()
    client.list_agents = AsyncMock(return_value=[])
    audit = AuditLogger('op-tst', root=tmp_path)

    await agent_tools.dispatch(
        'list_agents', {},
        client=client, allowlist=AbilityAllowlist(), audit=audit, mode='auto',
    )

    rows = [json.loads(l) for l in (tmp_path / 'op-tst.jsonl').read_text().splitlines() if l]
    events = [r['event'] for r in rows]
    assert 'tool_call' in events
    assert 'tool_result' in events


@pytest.mark.asyncio
async def test_dispatch_records_exceptions(tmp_path):
    client = MagicMock()
    client.list_agents = AsyncMock(side_effect=RuntimeError('boom'))
    audit = AuditLogger('op-tst', root=tmp_path)

    result = await agent_tools.dispatch(
        'list_agents', {},
        client=client, allowlist=AbilityAllowlist(), audit=audit, mode='auto',
    )

    assert 'error' in result
    assert 'boom' in result['error']
    rows = [json.loads(l) for l in (tmp_path / 'op-tst.jsonl').read_text().splitlines() if l]
    assert any(r['event'] == 'tool_error' for r in rows)


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_returns_error(tmp_path):
    audit = AuditLogger('op-tst', root=tmp_path)
    result = await agent_tools.dispatch(
        'made_up_tool', {},
        client=MagicMock(), allowlist=AbilityAllowlist(), audit=audit, mode='auto',
    )
    assert 'error' in result
    assert 'unknown tool' in result['error']
