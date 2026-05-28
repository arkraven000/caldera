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


def test_audit_logger_record_sync_swallows_unwritable_path():
    """Same fail-closed contract for the sync variant — used in places (planner
    construction, hook setup) where we can't await."""
    logger = AuditLogger('op-unwritable-sync', root='/nonexistent/path/that/cannot/be/created')
    logger.record_sync('event', {'k': 'v'})  # must not raise


@pytest.mark.asyncio
async def test_audit_logger_serializes_non_json_values(tmp_path):
    """Payload values that aren't natively JSON-serializable (datetime, set,
    custom objects) must be coerced via default=str, not crash the planner."""
    import datetime
    logger = AuditLogger('op-types', root=tmp_path)

    class Thing:
        def __str__(self):
            return 'thing-repr'

    await logger.record('event', {
        'when': datetime.datetime(2026, 1, 1, 12, 0, 0),
        'tags': {'a', 'b'},  # set
        'obj': Thing(),
    })
    rows = [json.loads(l) for l in (tmp_path / 'op-types.jsonl').read_text().splitlines() if l]
    assert rows[0]['payload']['obj'] == 'thing-repr'
    assert '2026' in rows[0]['payload']['when']


@pytest.mark.asyncio
async def test_audit_logger_preserves_event_order(tmp_path):
    logger = AuditLogger('op-order', root=tmp_path)
    for i in range(10):
        await logger.record('event', {'i': i})
    rows = [json.loads(l) for l in (tmp_path / 'op-order.jsonl').read_text().splitlines() if l]
    assert [r['payload']['i'] for r in rows] == list(range(10))


@pytest.mark.asyncio
async def test_audit_logger_metadata_per_record(tmp_path):
    """Every row must carry ts, operation_id, event, decided_by, pid, payload."""
    logger = AuditLogger('op-meta', root=tmp_path)
    await logger.record('e', {'k': 1}, decided_by='operator')
    row = json.loads((tmp_path / 'op-meta.jsonl').read_text().splitlines()[0])
    assert set(row.keys()) >= {'ts', 'operation_id', 'event', 'decided_by', 'pid', 'payload'}
    assert row['decided_by'] == 'operator'
    assert row['operation_id'] == 'op-meta'
    assert row['payload'] == {'k': 1}
