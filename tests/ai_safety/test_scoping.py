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


def test_slash_32_single_host_boundary():
    """A /32 must permit exactly one host — not the surrounding /31."""
    s = TargetScope(cidrs=['10.0.0.5/32'])
    assert s.permits_ip('10.0.0.5') is True
    assert s.permits_ip('10.0.0.4') is False
    assert s.permits_ip('10.0.0.6') is False


def test_slash_31_two_host_boundary():
    s = TargetScope(cidrs=['10.0.0.4/31'])
    assert s.permits_ip('10.0.0.4') is True
    assert s.permits_ip('10.0.0.5') is True
    assert s.permits_ip('10.0.0.6') is False


def test_cidr_with_host_bits_not_strict():
    """strict=False means we accept '10.0.0.5/24' (host bits set) without error."""
    s = TargetScope(cidrs=['10.0.0.5/24'])
    assert s.permits_ip('10.0.0.99') is True
    assert s.permits_ip('10.0.1.1') is False


def test_ipv6_cidr_matches_v6_address():
    s = TargetScope(cidrs=['2001:db8::/32'])
    assert s.permits_ip('2001:db8:0:1::1') is True
    assert s.permits_ip('2001:dba::1') is False


def test_v4_in_v6_scope_is_denied():
    """A v6-only scope must NOT match v4 addresses (ipaddress raises TypeError on cross-version 'in')."""
    s = TargetScope(cidrs=['2001:db8::/32'])
    assert s.permits_ip('10.0.0.1') is False


def test_paws_only_scope_permits_any_ip_but_filters_paws():
    s = TargetScope(paws=['paw-1'])
    assert s.permits_paw('paw-1') is True
    assert s.permits_paw('paw-2') is False
    # No cidrs set → permits_ip permissive.
    assert s.permits_ip('8.8.8.8') is True


def test_cidrs_only_scope_documents_asymmetric_paw_semantics():
    """ASYMMETRY: permits_ip checks `self.cidrs` only (each dimension independent),
    but permits_paw checks `is_restrictive` (= paws OR cidrs). Net effect: setting
    cidrs but not paws blocks ALL paws — operators who set a CIDR scope without a
    paw scope must explicitly add the paws they expect to operate on.

    This test pins the current behavior so a future fix is intentional, not silent."""
    s = TargetScope(cidrs=['10.0.0.0/8'])
    # CIDR scope alone restricts paws too — counter-intuitive but the current contract.
    assert s.permits_paw('any') is False
    assert s.permits_ip('10.1.2.3') is True
    assert s.permits_ip('8.8.8.8') is False


def test_from_config_handles_none_and_empty():
    assert TargetScope.from_config(None).is_restrictive is False
    assert TargetScope.from_config({}).is_restrictive is False


def test_from_config_builds_both_sets():
    s = TargetScope.from_config({'paws': ['a'], 'cidrs': ['10.0.0.0/8']})
    assert s.permits_paw('a') is True
    assert s.permits_ip('10.0.0.1') is True
