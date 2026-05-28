import time

from plugins.mcp_server.app.approval_tokens import ApprovalTokenStore


def test_token_round_trip():
    store = ApprovalTokenStore(ttl_seconds=60)
    token = store.mint('op1', 'abil1', 'paw1', 'link1')
    ok, msg = store.consume(token, 'op1', 'link1')
    assert ok is True
    assert msg == 'approved'


def test_token_is_single_use():
    store = ApprovalTokenStore(ttl_seconds=60)
    token = store.mint('op1', 'a', 'p', 'l1')
    assert store.consume(token, 'op1', 'l1')[0] is True
    assert store.consume(token, 'op1', 'l1')[0] is False


def test_token_rejects_mismatched_operation():
    store = ApprovalTokenStore(ttl_seconds=60)
    token = store.mint('op1', 'a', 'p', 'l1')
    ok, msg = store.consume(token, 'op2', 'l1')
    assert ok is False
    assert 'operation' in msg


def test_token_rejects_mismatched_link():
    store = ApprovalTokenStore(ttl_seconds=60)
    token = store.mint('op1', 'a', 'p', 'l1')
    ok, msg = store.consume(token, 'op1', 'l2')
    assert ok is False
    assert 'link' in msg


def test_token_expires():
    store = ApprovalTokenStore(ttl_seconds=0)
    token = store.mint('op1', 'a', 'p', 'l1')
    time.sleep(0.01)
    ok, msg = store.consume(token, 'op1', 'l1')
    assert ok is False
    assert 'unknown or expired' in msg


def test_unknown_token_rejected():
    store = ApprovalTokenStore()
    ok, msg = store.consume('not-a-real-token', 'op1', 'l1')
    assert ok is False
