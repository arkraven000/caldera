from app.ai_safety import TargetScope


def test_empty_scope_permits_everything():
    s = TargetScope()
    assert s.is_restrictive is False
    assert s.permits_paw('any-paw') is True
    assert s.permits_ip('1.2.3.4') is True


def test_paw_allowlist_restricts():
    s = TargetScope(paws=['agent1', 'agent2'])
    assert s.permits_paw('agent1') is True
    assert s.permits_paw('agent3') is False


def test_cidr_allowlist_restricts():
    s = TargetScope(cidrs=['10.0.0.0/8', '192.168.0.0/16'])
    assert s.permits_ip('10.1.2.3') is True
    assert s.permits_ip('192.168.5.5') is True
    assert s.permits_ip('8.8.8.8') is False


def test_invalid_ip_is_denied():
    s = TargetScope(cidrs=['10.0.0.0/8'])
    assert s.permits_ip('not-an-ip') is False


def test_invalid_cidr_ignored():
    s = TargetScope(cidrs=['bad-cidr', '10.0.0.0/8'])
    assert s.permits_ip('10.1.1.1') is True
