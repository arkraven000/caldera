"""Behavior tests for plugins/llm_planner that don't require a real Anthropic API key.

We verify:
- Without ANTHROPIC_API_KEY, the planner constructs but immediately halts (next_bucket=None).
- With the SDK / key present, the planner can be constructed; we then exercise its
  decision pipeline with a mocked Anthropic client.
"""

import os
import sys
import types
import pytest
from unittest.mock import AsyncMock, MagicMock

from plugins.llm_planner.app.llm_planner import LogicalPlanner


def _stub_anthropic_module():
    """Install a stub anthropic module so get_async_client() succeeds."""
    if 'anthropic' in sys.modules:
        return
    mod = types.ModuleType('anthropic')

    class _Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.messages = MagicMock()

    mod.AsyncAnthropic = _Client
    sys.modules['anthropic'] = mod


class _StubAbility:
    def __init__(self, ability_id, tactic='discovery', technique_id='T1083'):
        self.ability_id = ability_id
        self.name = f'ability-{ability_id}'
        self.tactic = tactic
        self.technique_id = technique_id
        self.description = ''
        self.executors = []


class _StubLink:
    def __init__(self, ability, paw='paw1'):
        self.id = f'link-{ability.ability_id}'
        self.ability = ability
        self.paw = paw
        self.executor = None
        self.score = 0
        self.states = {'DISCARD': -2, 'SUCCESS': 0, 'HIGH_VIZ': -5}
        self.status = -3
        self.finish = False


class _StubOperation:
    def __init__(self):
        self.id = 'op-test'
        self.name = 'test-op'
        self.state = 'running'
        self.agents = []
        self.chain = []
        self.adversary = MagicMock(name='adv', objective=None)
        self.adversary.name = 'adv'

    def add_link(self, link):
        self.chain.append(link)

    async def all_facts(self):
        return []

    async def apply(self, link):
        link.status = 0
        self.chain.append(link)
        return link.id

    async def wait_for_links_completion(self, ids):
        return None


class _StubPlanningSvc:
    def __init__(self, links):
        self._links = links
        self.execute_planner = AsyncMock()

    async def get_links(self, operation=None, agent=None, **kw):
        return list(self._links)


def test_planner_fails_closed_without_api_key(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    sys.modules.pop('anthropic', None)
    op = _StubOperation()
    svc = _StubPlanningSvc(links=[])
    planner = LogicalPlanner(op, svc, allowlist_tactics=['discovery'])
    assert planner.client is None
    assert planner.next_bucket is None


@pytest.mark.asyncio
async def test_planner_dry_run_discards_chosen_link(monkeypatch, tmp_path):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-stub')
    _stub_anthropic_module()

    abil_allowed = _StubAbility('aaa', tactic='discovery')
    abil_denied = _StubAbility('bbb', tactic='impact')
    links = [_StubLink(abil_allowed), _StubLink(abil_denied)]
    op = _StubOperation()
    svc = _StubPlanningSvc(links=links)
    planner = LogicalPlanner(
        op, svc, model='claude-sonnet-4-7', max_calls=1, dry_run=True,
        allowlist_tactics=['discovery'], audit_dir=str(tmp_path),
    )
    assert planner.client is not None

    async def fake_decide(*args, **kwargs):
        return {'ability_id': 'aaa', 'reasoning': 'r', 'confidence': 0.9, 'paw': 'paw1'}

    monkeypatch.setattr('plugins.llm_planner.app.llm_planner.decide', fake_decide)

    await planner.llm_step()

    assert planner.calls == 1
    assert len(op.chain) == 1
    assert op.chain[0].status == -2
    assert op.chain[0].ability.ability_id == 'aaa'


@pytest.mark.asyncio
async def test_planner_halts_when_no_permitted_links(monkeypatch, tmp_path):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-stub')
    _stub_anthropic_module()

    only_denied = [_StubLink(_StubAbility('x', tactic='impact'))]
    op = _StubOperation()
    svc = _StubPlanningSvc(links=only_denied)
    planner = LogicalPlanner(
        op, svc, model='claude-sonnet-4-7', max_calls=5,
        allowlist_tactics=['discovery'], audit_dir=str(tmp_path),
    )

    await planner.llm_step()

    assert planner.next_bucket is None
    assert planner.calls == 0


@pytest.mark.asyncio
async def test_planner_halts_at_max_calls(monkeypatch, tmp_path):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-stub')
    _stub_anthropic_module()

    op = _StubOperation()
    svc = _StubPlanningSvc(links=[_StubLink(_StubAbility('a'))])
    planner = LogicalPlanner(op, svc, max_calls=0, allowlist_tactics=['discovery'],
                             audit_dir=str(tmp_path))

    await planner.llm_step()
    assert planner.next_bucket is None
