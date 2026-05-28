"""Tests for tools.claude_agent.approval — interactive operator gate.

In interactive mode, every mutating tool call hits this gate. The behavior matters:
- 'n' / 'no' / unrecognized / EOF → MUST decline (fail closed)
- 'e' / 'edit' followed by invalid JSON → MUST decline (don't silently keep input)
- 'e' followed by empty line → keep original input (operator inspection only)
- dry-run / auto modes → bypass the gate (intentional — dry-run is read-only,
   auto is opted-in autonomy)
"""

import io
import json

import pytest

from tools.claude_agent.approval import (
    MUTATING_TOOLS,
    needs_approval,
    prompt_operator,
)


@pytest.mark.parametrize('tool', sorted(MUTATING_TOOLS))
def test_needs_approval_in_interactive_for_every_mutating_tool(tool):
    assert needs_approval(tool, 'interactive') is True


@pytest.mark.parametrize('tool', ['list_abilities', 'get_operation', 'get_facts',
                                  'list_agents', 'list_potential_links', 'summarize',
                                  'stop_operation'])
def test_needs_approval_skips_read_only_tools(tool):
    assert needs_approval(tool, 'interactive') is False


def test_needs_approval_skipped_in_dry_run():
    for tool in MUTATING_TOOLS:
        assert needs_approval(tool, 'dry-run') is False


def test_needs_approval_skipped_in_auto():
    for tool in MUTATING_TOOLS:
        assert needs_approval(tool, 'auto') is False


def test_prompt_operator_approves_on_y(monkeypatch):
    monkeypatch.setattr('sys.stdin', io.StringIO('y\n'))
    approved, edited, msg = prompt_operator('execute_link', {'paw': 'p1'})
    assert approved is True
    assert edited == {'paw': 'p1'}
    assert msg == 'approved'


def test_prompt_operator_approves_on_yes(monkeypatch):
    monkeypatch.setattr('sys.stdin', io.StringIO('yes\n'))
    approved, _, _ = prompt_operator('execute_link', {})
    assert approved is True


def test_prompt_operator_declines_on_n(monkeypatch):
    monkeypatch.setattr('sys.stdin', io.StringIO('n\n'))
    approved, edited, msg = prompt_operator('execute_link', {})
    assert approved is False
    assert edited is None
    assert msg == 'operator declined'


def test_prompt_operator_declines_on_unrecognized_choice(monkeypatch):
    # Unrecognized input (e.g. "maybe") must NOT approve — fail closed.
    monkeypatch.setattr('sys.stdin', io.StringIO('maybe\n'))
    approved, _, _ = prompt_operator('execute_link', {})
    assert approved is False


def test_prompt_operator_declines_on_eof(monkeypatch):
    # Empty stdin (closed pipe / piped input exhausted) — fail closed.
    monkeypatch.setattr('sys.stdin', io.StringIO(''))
    approved, _, msg = prompt_operator('execute_link', {})
    assert approved is False


def test_prompt_operator_edit_replaces_input(monkeypatch):
    new_input = {'paw': 'edited', 'ability_id': 'a2'}
    monkeypatch.setattr('sys.stdin', io.StringIO(f'e\n{json.dumps(new_input)}\n'))
    approved, edited, msg = prompt_operator('execute_link', {'paw': 'original'})
    assert approved is True
    assert edited == new_input
    assert 'edits' in msg


def test_prompt_operator_edit_with_blank_keeps_input(monkeypatch):
    original = {'paw': 'original'}
    monkeypatch.setattr('sys.stdin', io.StringIO('e\n\n'))
    approved, edited, msg = prompt_operator('execute_link', original)
    assert approved is True
    assert edited == original
    assert 'unchanged' in msg


def test_prompt_operator_edit_with_bad_json_declines(monkeypatch):
    # Invalid JSON after 'e' must NOT silently keep the original — fail closed.
    monkeypatch.setattr('sys.stdin', io.StringIO('e\n{not json}\n'))
    approved, edited, msg = prompt_operator('execute_link', {'paw': 'p'})
    assert approved is False
    assert edited is None
    assert 'invalid JSON' in msg
