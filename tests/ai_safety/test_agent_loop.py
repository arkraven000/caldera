"""End-to-end test of the Anthropic tool-use loop with a fully stubbed Anthropic
client. Validates that:
- The catalog is sent as a cache_control block
- Tool calls dispatch through the safety layer
- A stop_operation tool call terminates the loop cleanly
- Token usage is aggregated across multiple Anthropic responses
"""

import json
import sys
import types
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.ai_safety import AbilityAllowlist


class _ToolUseBlock:
    type = 'tool_use'

    def __init__(self, id, name, input):
        self.id = id
        self.name = name
        self.input = input


class _Usage:
    def __init__(self, input_tokens=0, output_tokens=0, cache_creation=0, cache_read=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation
        self.cache_read_input_tokens = cache_read


class _Response:
    def __init__(self, content, usage=None, stop_reason='tool_use'):
        self.content = content
        self.usage = usage or _Usage()
        self.stop_reason = stop_reason


class _FakeAnthropic:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            return _Response(content=[], usage=_Usage(), stop_reason='end_turn')
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_agent_loop_terminates_on_stop_operation(tmp_path, monkeypatch):
    # Stub the anthropic SDK so get_async_client() succeeds without the real package.
    if 'anthropic' not in sys.modules:
        mod = types.ModuleType('anthropic')
        mod.AsyncAnthropic = lambda **kw: None
        sys.modules['anthropic'] = mod

    fake_caldera = MagicMock()
    fake_caldera.list_abilities = AsyncMock(return_value=[
        {'ability_id': 'a1', 'name': 'discovery-1', 'tactic': 'discovery',
         'technique_id': 'T1083', 'description': 'list files'},
    ])
    fake_caldera.get_operation = AsyncMock(return_value={'id': 'op1', 'name': 'test', 'state': 'running'})

    fake_anthropic = _FakeAnthropic(responses=[
        _Response(content=[_ToolUseBlock('tu1', 'get_operation', {'operation_id': 'op1'})],
                  usage=_Usage(input_tokens=100, output_tokens=20, cache_creation=80)),
        _Response(content=[_ToolUseBlock('tu2', 'stop_operation', {'reason': 'objective met'})],
                  usage=_Usage(input_tokens=120, output_tokens=10, cache_read=80)),
    ])

    from tools.claude_agent.agent_loop import run
    summary = await run(
        caldera_client=fake_caldera, anthropic_client=fake_anthropic,
        operation_id='op1', goal='test goal', mode='dry-run',
        max_steps=10, audit_dir=str(tmp_path),
        allowlist=AbilityAllowlist(),
    )

    assert summary['steps'] == 2
    assert 'stop_operation' in summary['stop_reason']
    assert summary['tokens']['cache_created'] == 80
    assert summary['tokens']['cache_read'] == 80
    assert summary['tokens']['input'] == 220


@pytest.mark.asyncio
async def test_agent_loop_caches_catalog_in_first_user_message(tmp_path):
    if 'anthropic' not in sys.modules:
        mod = types.ModuleType('anthropic')
        mod.AsyncAnthropic = lambda **kw: None
        sys.modules['anthropic'] = mod

    fake_caldera = MagicMock()
    fake_caldera.list_abilities = AsyncMock(return_value=[
        {'ability_id': 'a1', 'name': 'n', 'tactic': 't', 'technique_id': 'T', 'description': ''},
    ])

    fake_anthropic = _FakeAnthropic(responses=[
        _Response(content=[], stop_reason='end_turn'),
    ])

    from tools.claude_agent.agent_loop import run
    await run(
        caldera_client=fake_caldera, anthropic_client=fake_anthropic,
        operation_id='op1', goal='test', mode='dry-run',
        max_steps=5, audit_dir=str(tmp_path),
    )

    sent = fake_anthropic.calls[0]
    first_user_content = sent['messages'][0]['content']
    catalog_block = first_user_content[0]
    assert catalog_block['type'] == 'text'
    assert catalog_block.get('cache_control') == {'type': 'ephemeral'}
    assert 'CALDERA ABILITY CATALOG' in catalog_block['text']

    system_blocks = sent['system']
    assert system_blocks[0].get('cache_control') == {'type': 'ephemeral'}


@pytest.mark.asyncio
async def test_agent_loop_respects_max_steps(tmp_path):
    if 'anthropic' not in sys.modules:
        mod = types.ModuleType('anthropic')
        mod.AsyncAnthropic = lambda **kw: None
        sys.modules['anthropic'] = mod

    fake_caldera = MagicMock()
    fake_caldera.list_abilities = AsyncMock(return_value=[])

    # Always returns one tool_use, so we'd loop forever without max_steps.
    def _looping_response():
        return _Response(content=[_ToolUseBlock(f'tu', 'list_agents', {})])

    fake_anthropic = _FakeAnthropic(responses=[_looping_response() for _ in range(10)])
    fake_caldera.list_agents = AsyncMock(return_value=[])

    from tools.claude_agent.agent_loop import run
    summary = await run(
        caldera_client=fake_caldera, anthropic_client=fake_anthropic,
        operation_id='op1', goal='loop test', mode='dry-run',
        max_steps=3, audit_dir=str(tmp_path),
    )

    assert summary['steps'] == 3
    assert summary['stop_reason'] == 'max_steps_reached'
