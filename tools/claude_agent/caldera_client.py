"""Async REST client for Caldera APIv2.

Thin wrapper. No retries / no fancy logic — failure surfaces directly to the agent loop
so the LLM sees the error and can recover (or escalate to the operator).
"""

import asyncio

import aiohttp


class CalderaClientError(RuntimeError):
    pass


class CalderaClient:

    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=self.timeout, headers={'KEY': self.api_key})
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._session:
            await self._session.close()

    async def _request(self, method: str, path: str, **kw):
        url = f'{self.base_url}{path}'
        async with self._session.request(method, url, **kw) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise CalderaClientError(f'{method} {path} -> {resp.status}: {text[:500]}')
            if not text:
                return None
            try:
                import json
                return json.loads(text)
            except Exception:
                return text

    async def list_abilities(self, tactic: str = None, technique_id: str = None):
        rows = await self._request('GET', '/api/v2/abilities')
        if not isinstance(rows, list):
            return []
        if tactic:
            rows = [r for r in rows if (r.get('tactic') or '').lower() == tactic.lower()]
        if technique_id:
            rows = [r for r in rows if r.get('technique_id') == technique_id]
        return rows

    async def list_operations(self):
        return await self._request('GET', '/api/v2/operations') or []

    async def get_operation(self, operation_id: str):
        return await self._request('GET', f'/api/v2/operations/{operation_id}')

    async def list_agents(self):
        return await self._request('GET', '/api/v2/agents') or []

    async def get_facts(self, operation_id: str):
        op = await self.get_operation(operation_id)
        if not op:
            return []
        return op.get('facts', []) or []

    async def add_fact(self, operation_id: str, trait: str, value: str):
        body = {'trait': trait, 'value': value, 'source': operation_id}
        return await self._request('POST', '/api/v2/facts', json=body)

    async def list_links(self, operation_id: str):
        return await self._request('GET', f'/api/v2/operations/{operation_id}/links') or []

    async def propose_link(self, operation_id: str, ability_id: str, paw: str):
        body = {'paw': paw, 'ability': {'ability_id': ability_id}}
        return await self._request('POST', f'/api/v2/operations/{operation_id}/potential-links', json=body)

    async def execute_link(self, operation_id: str, link_payload: dict):
        return await self._request('POST', f'/api/v2/operations/{operation_id}/potential-links', json=link_payload)

    async def get_link(self, operation_id: str, link_id: str):
        links = await self.list_links(operation_id)
        for link in links:
            if link.get('id') == link_id:
                return link
        return None

    async def wait_for_link(self, operation_id: str, link_id: str, timeout_seconds: int = 120):
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            link = await self.get_link(operation_id, link_id)
            if link and link.get('status', -3) != -3:
                return link
            await asyncio.sleep(2)
        return {'status': 'timeout', 'link_id': link_id}

    async def patch_operation_state(self, operation_id: str, state: str):
        return await self._request('PATCH', f'/api/v2/operations/{operation_id}', json={'state': state})

    async def pause_operation(self, operation_id: str):
        return await self.patch_operation_state(operation_id, 'paused')

    async def resume_operation(self, operation_id: str):
        return await self.patch_operation_state(operation_id, 'running')
