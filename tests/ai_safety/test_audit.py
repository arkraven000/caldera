import json
import pytest

from app.ai_safety import AuditLogger


@pytest.mark.asyncio
async def test_audit_logger_writes_jsonl(tmp_path):
    logger = AuditLogger('op-test', root=tmp_path)
    await logger.record('tool_call', {'tool': 'list_abilities', 'mode': 'dry-run'})
    await logger.record('decision', {'ability_id': 'abc', 'confidence': 0.8})

    path = tmp_path / 'op-test.jsonl'
    assert path.exists()
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    assert len(rows) == 2
    assert rows[0]['event'] == 'tool_call'
    assert rows[0]['payload']['tool'] == 'list_abilities'
    assert rows[1]['event'] == 'decision'
    assert rows[1]['payload']['ability_id'] == 'abc'
    assert all('ts' in r and 'operation_id' in r and 'pid' in r for r in rows)


def test_audit_logger_sync_variant(tmp_path):
    logger = AuditLogger('op-sync', root=tmp_path)
    logger.record_sync('event', {'k': 'v'})
    path = tmp_path / 'op-sync.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    assert rows[0]['payload'] == {'k': 'v'}


@pytest.mark.asyncio
async def test_audit_logger_swallows_unwritable_path(tmp_path):
    """Audit failures must never propagate into the planner loop."""
    logger = AuditLogger('op-unwritable', root='/nonexistent/path/that/cannot/be/created')
    # Should not raise.
    await logger.record('event', {'k': 'v'})
