"""Concurrency tests for the AI safety primitives.

Best-practice tests for a security-critical safety layer should cover the cases
where multiple coroutines or processes touch the same primitive. We verify:

1. Approval-token mint is unique under concurrent calls (no collision in secrets).
2. A single token cannot be consumed twice when consume() is invoked concurrently
   (single-use property under a race).
3. The audit JSONL writer doesn't lose or interleave lines when multiple writers
   append concurrently — POSIX guarantees atomic appends for writes under
   PIPE_BUF, and we depend on that property to keep the audit log replayable.
"""

import asyncio
import json

import pytest

from app.ai_safety import AuditLogger
from plugins.mcp_server.app.approval_tokens import ApprovalTokenStore


@pytest.mark.asyncio
async def test_concurrent_mint_yields_unique_tokens():
    store = ApprovalTokenStore(ttl_seconds=60)
    tokens = await asyncio.gather(*[
        asyncio.to_thread(store.mint, 'op', f'a{i}', 'paw', f'l{i}')
        for i in range(64)
    ])
    assert len(set(tokens)) == 64


@pytest.mark.asyncio
async def test_concurrent_consume_is_single_use():
    # 100 racers attempt to consume the same token — exactly one wins.
    store = ApprovalTokenStore(ttl_seconds=60)
    token = store.mint('op', 'a', 'p', 'l1')

    def _consume():
        return store.consume(token, 'op', 'l1')

    results = await asyncio.gather(*[asyncio.to_thread(_consume) for _ in range(100)])
    wins = [r for r in results if r[0] is True]
    losses = [r for r in results if r[0] is False]
    assert len(wins) == 1
    assert len(losses) == 99


@pytest.mark.asyncio
async def test_concurrent_audit_writes_preserve_all_lines(tmp_path):
    logger = AuditLogger('op-conc', root=tmp_path)
    N = 50
    await asyncio.gather(*[
        logger.record('event', {'i': i, 'pad': 'x' * 32}) for i in range(N)
    ])
    rows = [json.loads(line) for line in (tmp_path / 'op-conc.jsonl').read_text().splitlines() if line]
    assert len(rows) == N
    seen_indices = sorted(r['payload']['i'] for r in rows)
    assert seen_indices == list(range(N))


@pytest.mark.asyncio
async def test_concurrent_audit_lines_are_complete_json(tmp_path):
    # Each line must parse on its own — no half-written records, no interleaving.
    logger = AuditLogger('op-conc-json', root=tmp_path)
    await asyncio.gather(*[
        logger.record('event', {'i': i, 'payload': 'A' * 64}) for i in range(40)
    ])
    for line in (tmp_path / 'op-conc-json.jsonl').read_text().splitlines():
        if not line:
            continue
        row = json.loads(line)
        assert row['event'] == 'event'
        assert isinstance(row['payload']['i'], int)
