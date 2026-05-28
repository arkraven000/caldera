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


@pytest.mark.asyncio
async def test_planner_execute_no_ops_without_client(monkeypatch, tmp_path):
    """If get_async_client() failed at __init__, execute() must return immediately
    without ever calling planning_svc.execute_planner — otherwise the planning loop
    would spin trying to run with no client."""
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    sys.modules.pop('anthropic', None)
    op = _StubOperation()
    svc = _StubPlanningSvc(links=[])
    planner = LogicalPlanner(op, svc, allowlist_tactics=['discovery'],
                             audit_dir=str(tmp_path))
    assert planner.client is None
    await planner.execute()
    svc.execute_planner.assert_not_called()


@pytest.mark.asyncio
async def test_planner_halts_when_decide_raises(monkeypatch, tmp_path):
    """If decide() raises (Anthropic API error, malformed response, etc.) the
    planner must fail closed — set next_bucket=None and audit a halt record."""
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-stub')
    _stub_anthropic_module()

    op = _StubOperation()
    svc = _StubPlanningSvc(links=[_StubLink(_StubAbility('a', tactic='discovery'))])
    planner = LogicalPlanner(op, svc, allowlist_tactics=['discovery'],
                             max_calls=5, audit_dir=str(tmp_path))

    async def boom(*args, **kwargs):
        raise RuntimeError('anthropic API 503')

    monkeypatch.setattr('plugins.llm_planner.app.llm_planner.decide', boom)

    await planner.llm_step()
    assert planner.next_bucket is None
    assert planner.calls == 0  # decide() raised before increment

    rows = _read_audit(tmp_path, op.id)
    halt_records = [r for r in rows if r['event'] == 'halt']
    assert any('decide_exception' in (r['payload'].get('reason') or '') for r in halt_records)


@pytest.mark.asyncio
async def test_planner_halts_when_model_picks_unknown_ability(monkeypatch, tmp_path):
    """The forced tool_use should constrain the model to one of the candidate
    ability_ids; if it picks an id we didn't offer (prompt cache desync, model
    bug, etc.) the planner must halt rather than guess."""
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-stub')
    _stub_anthropic_module()

    op = _StubOperation()
    svc = _StubPlanningSvc(links=[_StubLink(_StubAbility('real-ability', tactic='discovery'))])
    planner = LogicalPlanner(op, svc, allowlist_tactics=['discovery'],
                             max_calls=5, audit_dir=str(tmp_path))

    async def fake_decide(*args, **kwargs):
        return {'ability_id': 'hallucinated-id', 'reasoning': 'r', 'confidence': 0.9}

    monkeypatch.setattr('plugins.llm_planner.app.llm_planner.decide', fake_decide)

    await planner.llm_step()
    assert planner.next_bucket is None
    rows = _read_audit(tmp_path, op.id)
    assert any(r['event'] == 'halt' and
               r['payload'].get('reason') == 'model_chose_unknown_ability'
               for r in rows)


@pytest.mark.asyncio
async def test_planner_live_mode_applies_chosen_link(monkeypatch, tmp_path):
    """Non-dry-run: chosen link goes through op.apply() and the planner waits
    for completion. Verifies the live path so it doesn't drift from dry-run."""
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-stub')
    _stub_anthropic_module()

    target_ability = _StubAbility('go-live', tactic='discovery')
    link = _StubLink(target_ability)
    op = _StubOperation()
    svc = _StubPlanningSvc(links=[link])

    planner = LogicalPlanner(op, svc, dry_run=False, max_calls=2,
                             allowlist_tactics=['discovery'],
                             audit_dir=str(tmp_path))

    async def fake_decide(*args, **kwargs):
        return {'ability_id': 'go-live', 'reasoning': 'r', 'confidence': 1.0}

    monkeypatch.setattr('plugins.llm_planner.app.llm_planner.decide', fake_decide)

    await planner.llm_step()
    # Live: link goes through op.apply (which our stub sets status=0).
    assert link.status == 0
    assert link in op.chain
    rows = _read_audit(tmp_path, op.id)
    assert any(r['event'] == 'executed_live' for r in rows)


@pytest.mark.asyncio
async def test_planner_records_allowlist_filtering(monkeypatch, tmp_path):
    """Allowlist denials must be audited so an operator can audit *why* a
    candidate didn't reach the LLM."""
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-stub')
    _stub_anthropic_module()

    allowed = _StubLink(_StubAbility('a', tactic='discovery'))
    denied = _StubLink(_StubAbility('b', tactic='impact'))
    op = _StubOperation()
    svc = _StubPlanningSvc(links=[allowed, denied])
    planner = LogicalPlanner(op, svc, allowlist_tactics=['discovery'],
                             max_calls=1, audit_dir=str(tmp_path))

    async def fake_decide(*args, **kwargs):
        return {'ability_id': 'a', 'reasoning': 'r', 'confidence': 0.9}

    monkeypatch.setattr('plugins.llm_planner.app.llm_planner.decide', fake_decide)
    await planner.llm_step()

    rows = _read_audit(tmp_path, op.id)
    filtered = [r for r in rows if r['event'] == 'filtered']
    assert len(filtered) == 1
    assert filtered[0]['payload']['denied_count'] == 1


def _read_audit(tmp_path, op_id):
    import json
    p = tmp_path / f'{op_id}.jsonl'
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l]
