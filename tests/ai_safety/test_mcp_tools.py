"""Tests for plugins/mcp_server/app/tools.CalderaMCPTools — the facade Caldera-side
that MCP tool definitions delegate to. We stub Caldera services with MagicMock-based
fakes so we don't need a running aiohttp server."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.ai_safety import AbilityAllowlist
from plugins.mcp_server.app.tools import CalderaMCPTools


class _StubAbility:
    def __init__(self, ability_id, tactic='discovery', technique_id='T1083', name='probe'):
        self.ability_id = ability_id
        self.tactic = tactic
        self.technique_id = technique_id
        self.name = name
        self.technique_name = 'tname'
        self.description = ''
        self.executors = []


class _StubExecutor:
    platform = 'linux'


class _StubLink:
    def __init__(self, link_id, ability, paw='paw1'):
        self.id = link_id
        self.ability = ability
        self.paw = paw
        self.executor = _StubExecutor()
        self.score = 0
        self.plaintext_command = 'whoami'
        self.command = 'd2hvYW1p'
        self.status = -3
        self.states = {'DISCARD': -2}


class _StubAgent:
    def __init__(self, paw):
        self.paw = paw
        self.host = 'host1'
        self.platform = 'linux'
        self.username = 'user'
        self.privilege = 'User'
        self.trusted = True
        self.last_seen = '2026-05-28'


class _StubOperation:
    def __init__(self, op_id='op1'):
        self.id = op_id
        self.name = 'test-op'
        self.state = 'running'
        self.adversary = MagicMock(name='adv')
        self.adversary.name = 'adv'
        self.planner = MagicMock()
        self.planner.name = 'manual'
        self.agents = [_StubAgent('paw1')]
        self.chain = []
        self._facts = []

    async def all_facts(self):
        return self._facts

    async def apply(self, link):
        link.status = 0
        self.chain.append(link)
        return link.id

    async def wait_for_links_completion(self, ids):
        return None


def _services(operations, links_for_op=None):
    data_svc = MagicMock()

    async def locate(name, match=None):
        if name == 'operations':
            if match and 'id' in match:
                return [o for o in operations if o.id == match['id']]
            return operations
        return []

    data_svc.locate = locate

    planning_svc = MagicMock()

    async def get_links(operation, agent=None, **kw):
        if links_for_op is None:
            return []
        return links_for_op.get(operation.id, [])

    planning_svc.get_links = get_links

    return {'data_svc': data_svc, 'planning_svc': planning_svc}


@pytest.mark.asyncio
async def test_list_operations_returns_compact_view():
    op = _StubOperation('op1')
    tools = CalderaMCPTools(_services([op]))
    rows = await tools.list_operations()
    assert rows == [{'id': 'op1', 'name': 'test-op', 'state': 'running', 'planner': 'manual'}]


@pytest.mark.asyncio
async def test_get_operation_includes_recent_links():
    op = _StubOperation('op1')
    link = _StubLink('l1', _StubAbility('a1'))
    op.chain.append(link)
    tools = CalderaMCPTools(_services([op]))
    view = await tools.get_operation('op1')
    assert view['id'] == 'op1'
    assert view['chain_length'] == 1
    assert view['recent_links'][0]['ability_id'] == 'a1'


@pytest.mark.asyncio
async def test_get_operation_missing_returns_error():
    tools = CalderaMCPTools(_services([]))
    result = await tools.get_operation('nope')
    assert 'error' in result


@pytest.mark.asyncio
async def test_propose_next_link_returns_token_for_runnable_ability(tmp_path):
    op = _StubOperation('op1')
    link = _StubLink('l1', _StubAbility('a1', tactic='discovery'))
    tools = CalderaMCPTools(
        _services([op], links_for_op={'op1': [link]}),
        allowlist=AbilityAllowlist(tactics=['discovery']),
        audit_root=str(tmp_path),
    )
    result = await tools.propose_next_link('op1', 'a1', 'paw1')
    assert 'approval_token' in result
    assert result['link_id'] == 'l1'
    assert result['paw'] == 'paw1'


@pytest.mark.asyncio
async def test_propose_next_link_denied_by_allowlist(tmp_path):
    op = _StubOperation('op1')
    link = _StubLink('l1', _StubAbility('a1', tactic='impact'))
    tools = CalderaMCPTools(
        _services([op], links_for_op={'op1': [link]}),
        allowlist=AbilityAllowlist(tactics=['discovery']),
        audit_root=str(tmp_path),
    )
    result = await tools.propose_next_link('op1', 'a1', 'paw1')
    assert 'error' in result
    assert 'denied by allowlist' in result['error']


@pytest.mark.asyncio
async def test_propose_next_link_unknown_ability_returns_error(tmp_path):
    op = _StubOperation('op1')
    tools = CalderaMCPTools(
        _services([op], links_for_op={'op1': []}),
        audit_root=str(tmp_path),
    )
    result = await tools.propose_next_link('op1', 'unknown-id', 'paw1')
    assert 'error' in result
    assert 'not currently runnable' in result['error']


@pytest.mark.asyncio
async def test_approve_and_execute_link_requires_valid_token(tmp_path):
    op = _StubOperation('op1')
    tools = CalderaMCPTools(_services([op]), audit_root=str(tmp_path))
    result = await tools.approve_and_execute_link('op1', 'l1', 'invalid-token')
    assert 'error' in result


@pytest.mark.asyncio
async def test_propose_then_approve_full_round_trip(tmp_path):
    op = _StubOperation('op1')
    link = _StubLink('l1', _StubAbility('a1', tactic='discovery'))
    tools = CalderaMCPTools(
        _services([op], links_for_op={'op1': [link]}),
        allowlist=AbilityAllowlist(tactics=['discovery']),
        audit_root=str(tmp_path),
    )
    propose = await tools.propose_next_link('op1', 'a1', 'paw1')
    token = propose['approval_token']

    result = await tools.approve_and_execute_link('op1', 'l1', token)
    assert result['link_id'] == 'l1'
    assert result['status'] == 0
    assert link in op.chain


@pytest.mark.asyncio
async def test_propose_next_link_unknown_agent_returns_error(tmp_path):
    op = _StubOperation('op1')
    link = _StubLink('l1', _StubAbility('a1', tactic='discovery'))
    tools = CalderaMCPTools(
        _services([op], links_for_op={'op1': [link]}),
        audit_root=str(tmp_path),
    )
    result = await tools.propose_next_link('op1', 'a1', 'paw-does-not-exist')
    assert 'error' in result
    assert 'not attached' in result['error']


@pytest.mark.asyncio
async def test_propose_next_link_unknown_operation_returns_error(tmp_path):
    tools = CalderaMCPTools(_services([]), audit_root=str(tmp_path))
    result = await tools.propose_next_link('nonexistent', 'a1', 'paw1')
    assert 'error' in result
    assert 'not found' in result['error']


@pytest.mark.asyncio
async def test_approve_and_execute_rejects_after_op_disappears(tmp_path):
    """Token was minted against a real op; by execute time the op is gone.
    Token consumption succeeds (it matched), but the executor still fails closed
    because the op can't be located."""
    op = _StubOperation('op1')
    link = _StubLink('l1', _StubAbility('a1', tactic='discovery'))
    tools = CalderaMCPTools(
        _services([op], links_for_op={'op1': [link]}),
        allowlist=AbilityAllowlist(tactics=['discovery']),
        audit_root=str(tmp_path),
    )
    propose = await tools.propose_next_link('op1', 'a1', 'paw1')
    token = propose['approval_token']

    # Op vanishes between mint and execute.
    tools.data_svc.locate = (lambda **kw: _make_async_returning([]))()

    result = await tools.approve_and_execute_link('op1', 'l1', token)
    assert 'error' in result
    assert 'not found' in result['error']


@pytest.mark.asyncio
async def test_approve_and_execute_rebuilds_link_when_not_in_chain(tmp_path):
    """If the link was minted but not yet in op.chain (operator approved a
    proposed-but-uncommitted link), the tool must use _rebuild_link to fetch
    a fresh candidate matching the link_id."""
    op = _StubOperation('op1')
    link = _StubLink('l1', _StubAbility('a1', tactic='discovery'))
    # Note: link is NOT placed in op.chain. propose still mints a token.
    tools = CalderaMCPTools(
        _services([op], links_for_op={'op1': [link]}),
        allowlist=AbilityAllowlist(tactics=['discovery']),
        audit_root=str(tmp_path),
    )
    propose = await tools.propose_next_link('op1', 'a1', 'paw1')
    token = propose['approval_token']

    # Clear the chain so _rebuild_link path is exercised.
    op.chain = []
    result = await tools.approve_and_execute_link('op1', 'l1', token)
    assert result['link_id'] == 'l1'


@pytest.mark.asyncio
async def test_approve_and_execute_invalid_token_audit_records_denial(tmp_path):
    op = _StubOperation('op1')
    tools = CalderaMCPTools(_services([op]), audit_root=str(tmp_path))
    await tools.approve_and_execute_link('op1', 'l1', 'bogus-token')
    log_file = tmp_path / 'op1.jsonl'
    rows = [json.loads(l) for l in log_file.read_text().splitlines() if l]
    events = [r['event'] for r in rows]
    assert 'mcp_execute_denied' in events


@pytest.mark.asyncio
async def test_summarize_operation_aggregates_tactics_and_facts(tmp_path):
    op = _StubOperation('op1')
    link1 = _StubLink('l1', _StubAbility('a1', tactic='discovery'))
    link2 = _StubLink('l2', _StubAbility('a2', tactic='collection'))
    op.chain.extend([link1, link2])
    op._facts = [MagicMock(trait='host', value='h1', source='op', score=1)]

    tools = CalderaMCPTools(_services([op]), audit_root=str(tmp_path))
    summary = await tools.summarize_operation('op1')
    assert summary['id'] == 'op1'
    assert summary['facts_total'] == 1
    assert set(summary['tactics_executed']) == {'collection', 'discovery'}


@pytest.mark.asyncio
async def test_list_abilities_filters_by_tactic(tmp_path):
    op = _StubOperation('op1')
    services = _services([op])

    class _Ab:
        def __init__(self, id_, tactic, tech):
            self.ability_id = id_
            self.tactic = tactic
            self.technique_id = tech
            self.name = id_
            self.technique_name = ''
            self.description = ''
            self.executors = []

    async def locate(name, match=None):
        if name == 'abilities':
            return [_Ab('a', 'discovery', 'T1'), _Ab('b', 'impact', 'T2')]
        if name == 'operations':
            return [op]
        return []

    services['data_svc'].locate = locate
    tools = CalderaMCPTools(services, audit_root=str(tmp_path))
    rows = await tools.list_abilities(tactic='Discovery')  # mixed case
    assert len(rows) == 1
    assert rows[0]['ability_id'] == 'a'


@pytest.mark.asyncio
async def test_get_facts_handles_missing_operation(tmp_path):
    tools = CalderaMCPTools(_services([]), audit_root=str(tmp_path))
    assert await tools.get_facts('nonexistent') == []


@pytest.mark.asyncio
async def test_get_facts_swallows_all_facts_exception(tmp_path):
    """all_facts() can raise mid-operation (e.g. fact store transient error).
    The tool must surface an empty list, not crash the MCP server."""
    op = _StubOperation('op1')

    async def boom():
        raise RuntimeError('fact store down')
    op.all_facts = boom

    tools = CalderaMCPTools(_services([op]), audit_root=str(tmp_path))
    assert await tools.get_facts('op1') == []


@pytest.mark.asyncio
async def test_list_agents_filtered_by_operation(tmp_path):
    op1 = _StubOperation('op1')
    op2 = _StubOperation('op2')
    op1.agents = [_StubAgent('paw-a')]
    op2.agents = [_StubAgent('paw-b'), _StubAgent('paw-c')]
    services = _services([op1, op2])
    tools = CalderaMCPTools(services, audit_root=str(tmp_path))
    rows = await tools.list_agents(operation_id='op2')
    assert {r['paw'] for r in rows} == {'paw-b', 'paw-c'}


def _make_async_returning(value):
    async def _f(*a, **kw):
        return value
    return _f
