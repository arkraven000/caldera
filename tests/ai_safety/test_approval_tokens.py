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


def test_op_mismatch_evicts_token_so_replay_against_correct_op_fails():
    """If a token is presented with the wrong operation_id, it must be evicted —
    otherwise an attacker who guessed the op could retry indefinitely."""
    store = ApprovalTokenStore(ttl_seconds=60)
    token = store.mint('op1', 'a', 'p', 'l1')
    # Attacker probes with wrong op_id — must fail AND evict.
    store.consume(token, 'wrong-op', 'l1')
    # Now even the correct op cannot consume it.
    ok, _ = store.consume(token, 'op1', 'l1')
    assert ok is False


def test_link_id_mismatch_does_not_evict_token():
    """Conversely, a link_id mismatch is treated as recoverable (caller retries with
    the correct link); the token stays valid until TTL. Verify so behavior doesn't drift."""
    store = ApprovalTokenStore(ttl_seconds=60)
    token = store.mint('op1', 'a', 'p', 'l1')
    store.consume(token, 'op1', 'wrong-link')
    ok, _ = store.consume(token, 'op1', 'l1')
    assert ok is True


def test_multiple_tokens_coexist_independently():
    store = ApprovalTokenStore(ttl_seconds=60)
    t1 = store.mint('op1', 'a', 'p', 'l1')
    t2 = store.mint('op1', 'a', 'p', 'l2')
    t3 = store.mint('op2', 'b', 'q', 'l3')
    assert len({t1, t2, t3}) == 3
    assert store.consume(t2, 'op1', 'l2')[0] is True
    # Consuming t2 must NOT invalidate t1 or t3.
    assert store.consume(t1, 'op1', 'l1')[0] is True
    assert store.consume(t3, 'op2', 'l3')[0] is True


def test_gc_removes_expired_tokens_on_next_mint():
    """The GC sweep runs on each mint/consume — expired entries shouldn't linger
    in memory forever, even when nobody attempts to consume them."""
    store = ApprovalTokenStore(ttl_seconds=0)
    token = store.mint('op1', 'a', 'p', 'l1')
    time.sleep(0.01)
    # Mint a fresh token to trigger the GC sweep.
    store.mint('op2', 'b', 'q', 'l2')
    assert token not in store._tokens
