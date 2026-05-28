"""Tests for the standalone client (Variation B).

We stub out aiohttp at the request level so we can assert exact URLs, methods, and
payloads without standing up a real server.
"""

import pytest
from unittest.mock import AsyncMock, patch

from tools.claude_agent.caldera_client import CalderaClient, CalderaClientError


class _FakeResponse:
    def __init__(self, status, text):
        self.status = status
        self._text = text

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None


class _FakeSession:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []
        self.closed = False

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        if not self.scripted:
            return _FakeResponse(404, '')
        status, body = self.scripted.pop(0)
        return _FakeResponse(status, body)

    async def close(self):
        self.closed = True


def _patched_client(monkeypatch, scripted):
    session = _FakeSession(scripted)

    class _DummySession:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            await session.close()

    monkeypatch.setattr('aiohttp.ClientSession', lambda *a, **kw: session)
    return session


@pytest.mark.asyncio
async def test_list_abilities_filters_client_side(monkeypatch):
    session = _patched_client(monkeypatch, scripted=[
        (200, '[{"ability_id":"a1","tactic":"discovery","technique_id":"T1"},'
              '{"ability_id":"a2","tactic":"impact","technique_id":"T2"}]'),
    ])
    async with CalderaClient('http://server', 'KEY') as c:
        rows = await c.list_abilities(tactic='discovery')
    assert len(rows) == 1
    assert rows[0]['ability_id'] == 'a1'
    method, url, _ = session.calls[0]
    assert method == 'GET'
    assert url.endswith('/api/v2/abilities')


@pytest.mark.asyncio
async def test_propose_link_filters_get_response(monkeypatch):
    """propose_link MUST be a GET (then filter) — a POST would execute the link."""
    candidates = [
        {'ability': {'ability_id': 'a1'}, 'paw': 'p1', 'executor': {'name': 'sh', 'command': 'ls'}},
        {'ability': {'ability_id': 'a2'}, 'paw': 'p1', 'executor': {'name': 'sh', 'command': 'whoami'}},
    ]
    import json
    session = _patched_client(monkeypatch, scripted=[(200, json.dumps(candidates))])
    async with CalderaClient('http://server', 'KEY') as c:
        result = await c.propose_link('op1', 'a2', 'p1')
    method, url, _ = session.calls[0]
    assert method == 'GET'
    assert '/potential-links/p1' in url
    assert result['ability']['ability_id'] == 'a2'
    assert result['executor']['command'] == 'whoami'


@pytest.mark.asyncio
async def test_propose_link_returns_error_when_no_match(monkeypatch):
    _patched_client(monkeypatch, scripted=[(200, '[]')])
    async with CalderaClient('http://server', 'KEY') as c:
        result = await c.propose_link('op1', 'missing', 'p1')
    assert 'error' in result


@pytest.mark.asyncio
async def test_execute_link_rejects_incomplete_payload(monkeypatch):
    _patched_client(monkeypatch, scripted=[])
    async with CalderaClient('http://server', 'KEY') as c:
        result = await c.execute_link('op1', {'paw': 'p1'})
    assert 'error' in result


@pytest.mark.asyncio
async def test_execute_link_posts_full_payload(monkeypatch):
    full = {'paw': 'p1', 'executor': {'name': 'sh', 'command': 'ls'}, 'ability': {'ability_id': 'a1'}}
    session = _patched_client(monkeypatch, scripted=[(200, '{"id":"link1","status":-3}')])
    async with CalderaClient('http://server', 'KEY') as c:
        result = await c.execute_link('op1', full)
    method, url, kw = session.calls[0]
    assert method == 'POST'
    assert url.endswith('/api/v2/operations/op1/potential-links')
    assert kw['json'] == full
    assert result['id'] == 'link1'


@pytest.mark.asyncio
async def test_pause_resume_state_transitions(monkeypatch):
    session = _patched_client(monkeypatch, scripted=[
        (200, '{"state":"paused"}'),
        (200, '{"state":"running"}'),
    ])
    async with CalderaClient('http://server', 'KEY') as c:
        await c.pause_operation('op1')
        await c.resume_operation('op1')
    assert session.calls[0][2]['json'] == {'state': 'paused'}
    assert session.calls[1][2]['json'] == {'state': 'running'}


@pytest.mark.asyncio
async def test_http_error_surfaces(monkeypatch):
    _patched_client(monkeypatch, scripted=[(401, 'unauthorized')])
    async with CalderaClient('http://server', 'KEY') as c:
        with pytest.raises(CalderaClientError) as exc:
            await c.list_operations()
    assert '401' in str(exc.value)
