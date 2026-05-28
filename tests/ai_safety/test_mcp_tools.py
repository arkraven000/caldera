"""Tests for plugins/mcp_server/app/tools.CalderaMCPTools — the facade Caldera-side
that MCP tool definitions delegate to. We stub Caldera services with MagicMock-based
fakes so we don't need a running aiohttp server."""

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
