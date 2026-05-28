"""Tests for tools.claude_agent.cli — allowlist DSL parsing and entrypoint guardrails.

The CLI is the only thing standing between an operator and a live Caldera run, so
the safety preconditions enforced here (auto-mode requires an allowlist; both API
keys must be present) need to be mechanically enforced, not just documented.
"""

import sys

import pytest

from app.ai_safety import AbilityAllowlist
from tools.claude_agent.cli import _parse_allowlist, build_parser, main


def test_parse_allowlist_empty_string_yields_permissive():
    a = _parse_allowlist('')
    assert isinstance(a, AbilityAllowlist)
    assert a.is_restrictive is False


def test_parse_allowlist_handles_multiple_sections():
    a = _parse_allowlist('tactics=discovery,collection;deny_tactics=impact;ability_ids=x,y')
    assert 'discovery' in a.tactics
    assert 'collection' in a.tactics
    assert 'impact' in a.deny_tactics
    assert {'x', 'y'}.issubset(a.ability_ids)


def test_parse_allowlist_drops_malformed_sections():
    # A bare "discovery" with no key=value should be silently ignored rather than crashing.
    a = _parse_allowlist('discovery;tactics=collection')
    assert a.tactics == {'collection'}


def test_parse_allowlist_strips_whitespace():
    a = _parse_allowlist('tactics = discovery , collection ')
    assert a.tactics == {'discovery', 'collection'}


def test_parse_allowlist_handles_deny_technique_ids_unknown_key():
    # Unknown keys are dropped — the AbilityAllowlist constructor ignores them.
    a = _parse_allowlist('nonsense_key=foo;tactics=discovery')
    assert a.tactics == {'discovery'}


def test_parse_allowlist_technique_ids():
    a = _parse_allowlist('technique_ids=T1083,T1057')
    assert a.technique_ids == {'T1083', 'T1057'}


def test_build_parser_requires_operation_and_goal():
    parser = build_parser()
    # Missing --operation should fail.
    with pytest.raises(SystemExit):
        parser.parse_args(['--goal', 'x'])
    with pytest.raises(SystemExit):
        parser.parse_args(['--operation', 'op1'])


def test_build_parser_defaults_mode_to_dry_run():
    args = build_parser().parse_args(['--operation', 'op1', '--goal', 'g'])
    assert args.mode == 'dry-run'


def test_build_parser_mode_must_be_known_value():
    with pytest.raises(SystemExit):
        build_parser().parse_args(['--operation', 'op', '--goal', 'g', '--mode', 'YOLO'])


@pytest.mark.asyncio
async def test_main_refuses_auto_mode_without_allowlist(monkeypatch, capsys):
    monkeypatch.setenv('CALDERA_API_KEY', 'k')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk')
    monkeypatch.setattr(sys, 'argv', [
        'cli', '--operation', 'op1', '--goal', 'g', '--mode', 'auto', '--allowlist', '',
    ])
    rc = await main()
    assert rc == 2
    err = capsys.readouterr().err
    assert 'auto requires --allowlist' in err


@pytest.mark.asyncio
async def test_main_requires_caldera_api_key(monkeypatch, capsys):
    monkeypatch.delenv('CALDERA_API_KEY', raising=False)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk')
    monkeypatch.setattr(sys, 'argv', [
        'cli', '--operation', 'op1', '--goal', 'g', '--mode', 'dry-run',
    ])
    rc = await main()
    assert rc == 2
    assert 'CALDERA_API_KEY' in capsys.readouterr().err


@pytest.mark.asyncio
async def test_main_requires_anthropic_api_key(monkeypatch, capsys):
    monkeypatch.setenv('CALDERA_API_KEY', 'k')
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setattr(sys, 'argv', [
        'cli', '--operation', 'op1', '--goal', 'g', '--mode', 'dry-run',
    ])
    rc = await main()
    assert rc == 2
    assert 'ANTHROPIC_API_KEY' in capsys.readouterr().err
