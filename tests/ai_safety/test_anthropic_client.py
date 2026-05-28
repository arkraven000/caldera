"""Tests for app.ai_safety.anthropic_client — the SDK factory and cache_block helper.

Why this matters: every AI variation imports get_async_client(). It must fail closed
when the SDK is missing or the API key is unset, and the failure must be a typed
AnthropicNotConfigured (not a generic ImportError or KeyError) so callers can
distinguish "fork has no AI enabled" from real bugs.
"""

import sys
import types

import pytest

from app.ai_safety.anthropic_client import (
    AnthropicNotConfigured,
    cache_block,
    get_async_client,
)


def _install_fake_anthropic(monkeypatch):
    mod = types.ModuleType('anthropic')

    class _Client:
        def __init__(self, **kw):
            self.kw = kw

    mod.AsyncAnthropic = _Client
    monkeypatch.setitem(sys.modules, 'anthropic', mod)
    return _Client


def test_missing_api_key_raises_typed_error(monkeypatch):
    _install_fake_anthropic(monkeypatch)
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    with pytest.raises(AnthropicNotConfigured) as exc:
        get_async_client()
    assert 'ANTHROPIC_API_KEY' in str(exc.value)


def test_missing_sdk_raises_typed_error(monkeypatch):
    monkeypatch.delitem(sys.modules, 'anthropic', raising=False)

    real_import = __import__

    def fake_import(name, *a, **kw):
        if name == 'anthropic':
            raise ImportError('no module')
        return real_import(name, *a, **kw)

    monkeypatch.setattr('builtins.__import__', fake_import)

    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-stub')
    with pytest.raises(AnthropicNotConfigured) as exc:
        get_async_client()
    assert 'pip install anthropic' in str(exc.value)


def test_explicit_api_key_overrides_env(monkeypatch):
    _Client = _install_fake_anthropic(monkeypatch)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'env-key')
    client = get_async_client(api_key='explicit-key')
    assert isinstance(client, _Client)
    assert client.kw.get('api_key') == 'explicit-key'


def test_env_api_key_used_when_no_param(monkeypatch):
    _install_fake_anthropic(monkeypatch)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'env-key')
    client = get_async_client()
    assert client.kw.get('api_key') == 'env-key'


def test_cache_block_shape():
    block = cache_block('hello world')
    assert block['type'] == 'text'
    assert block['text'] == 'hello world'
    assert block['cache_control'] == {'type': 'ephemeral'}


def test_cache_block_preserves_empty_string():
    # An empty static block still gets cache_control — caller must guard against this.
    block = cache_block('')
    assert block['text'] == ''
    assert block['cache_control']['type'] == 'ephemeral'
