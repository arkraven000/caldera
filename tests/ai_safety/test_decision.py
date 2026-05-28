"""Tests for plugins/llm_planner/app/decision.decide — the single Anthropic call
per planner tick. We mock the client so we can assert exactly what the planner
sends and what it accepts back.

The contract we pin here:
1. The agent brief rides as the first system block (cache-hot across ticks).
2. The forced tool_choice constrains the model to `choose_next_link`.
3. The candidate list is sent as a cache_control block.
4. If the model returns no tool_use block, decide() raises so the planner can
   halt fail-closed rather than guessing.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _Usage:
    def __init__(self):
        self.input_tokens = 100
        self.output_tokens = 20
        self.cache_creation_input_tokens = 50
        self.cache_read_input_tokens = 0


class _ToolUseBlock:
    type = 'tool_use'

    def __init__(self, name, input_):
        self.name = name
        self.input = input_


class _Response:
    def __init__(self, content):
        self.content = content
        self.usage = _Usage()


def _fake_client(response_content):
    client = SimpleNamespace()
    client.messages = SimpleNamespace()
    client.messages.create = AsyncMock(return_value=_Response(response_content))
    return client


def _stub_link(ability_id='a1', tactic='discovery', paw='paw-1'):
    return SimpleNamespace(
        id=f'link-{ability_id}', paw=paw, score=0,
        executor=SimpleNamespace(platform='linux'),
        ability=SimpleNamespace(
            ability_id=ability_id, name=ability_id, tactic=tactic,
            technique_id='T1', description='', executors=[], technique_name='',
        ),
    )


def _stub_operation():
    op = SimpleNamespace(
        id='op1', name='test-op', state='running',
        agents=[], chain=[],
        adversary=SimpleNamespace(name='adv', objective=None),
    )

    async def all_facts():
        return []

    op.all_facts = all_facts
    return op


@pytest.mark.asyncio
async def test_decide_returns_tool_use_input_with_usage():
    from plugins.llm_planner.app.decision import decide

    client = _fake_client([_ToolUseBlock('choose_next_link', {
        'ability_id': 'a1', 'reasoning': 'r', 'confidence': 0.85, 'paw': 'paw-1',
    })])
    result = await decide(client, _stub_operation(), [_stub_link('a1')])
    assert result['ability_id'] == 'a1'
    assert result['confidence'] == 0.85
    assert result['_usage']['input_tokens'] == 100


@pytest.mark.asyncio
async def test_decide_raises_when_no_tool_use_block():
    """tool_choice is forced to choose_next_link, so any non-tool_use response
    is a contract violation — decide() must raise so the planner halts."""
    from plugins.llm_planner.app.decision import decide

    # Model returned only text — not allowed under forced tool_choice.
    text_block = SimpleNamespace(type='text', text='I refuse')
    client = _fake_client([text_block])
    with pytest.raises(RuntimeError) as exc:
        await decide(client, _stub_operation(), [_stub_link('a1')])
    assert 'no choose_next_link' in str(exc.value)


@pytest.mark.asyncio
async def test_decide_sends_brief_as_first_system_block():
    from plugins.llm_planner.app.decision import decide

    client = _fake_client([_ToolUseBlock('choose_next_link', {
        'ability_id': 'a1', 'reasoning': 'r', 'confidence': 0.5,
    })])
    await decide(client, _stub_operation(), [_stub_link('a1')])

    sent = client.messages.create.await_args.kwargs
    system_blocks = sent['system']
    # First block: the brief, cache-hot. Second: the planner-tick reminder.
    assert system_blocks[0]['cache_control'] == {'type': 'ephemeral'}
    assert len(system_blocks[0]['text']) > 1000
    assert 'caldera' in system_blocks[0]['text'].lower()
    # The PLANNER_SYSTEM reminder is the second block.
    assert len(system_blocks) >= 2
    assert 'choose exactly one' in system_blocks[1]['text'].lower()


@pytest.mark.asyncio
async def test_decide_forces_tool_choice():
    from plugins.llm_planner.app.decision import decide

    client = _fake_client([_ToolUseBlock('choose_next_link', {
        'ability_id': 'a1', 'reasoning': 'r', 'confidence': 0.5,
    })])
    await decide(client, _stub_operation(), [_stub_link('a1')])
    sent = client.messages.create.await_args.kwargs
    assert sent['tool_choice'] == {'type': 'tool', 'name': 'choose_next_link'}


@pytest.mark.asyncio
async def test_decide_sends_candidates_as_cache_block():
    from plugins.llm_planner.app.decision import decide

    client = _fake_client([_ToolUseBlock('choose_next_link', {
        'ability_id': 'a1', 'reasoning': 'r', 'confidence': 0.5,
    })])
    await decide(client, _stub_operation(), [_stub_link('a1'), _stub_link('a2')])

    sent = client.messages.create.await_args.kwargs
    user_content = sent['messages'][0]['content']
    candidates_block = user_content[0]
    assert candidates_block['cache_control'] == {'type': 'ephemeral'}
    assert 'CANDIDATE LINKS' in candidates_block['text']
    # Both candidates must be serialized into the block.
    assert 'a1' in candidates_block['text']
    assert 'a2' in candidates_block['text']


@pytest.mark.asyncio
async def test_decide_includes_denied_tactics_in_state_block():
    from plugins.llm_planner.app.decision import decide

    client = _fake_client([_ToolUseBlock('choose_next_link', {
        'ability_id': 'a1', 'reasoning': 'r', 'confidence': 0.5,
    })])
    await decide(client, _stub_operation(), [_stub_link('a1')], denied_tactics=['impact'])
    sent = client.messages.create.await_args.kwargs
    state_block_text = sent['messages'][0]['content'][1]['text']
    state_payload = json.loads(state_block_text)
    assert state_payload['denied_tactics'] == ['impact']
