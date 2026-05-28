import pytest

from app.ai_safety import AbilityAllowlist


class StubAbility:
    def __init__(self, ability_id, tactic, technique_id):
        self.ability_id = ability_id
        self.tactic = tactic
        self.technique_id = technique_id


class TestAbilityAllowlist:

    def test_empty_allowlist_is_permissive(self):
        a = AbilityAllowlist()
        assert a.is_restrictive is False
        ok, _ = a.permits(StubAbility('x', 'discovery', 'T1083'))
        assert ok is True

    def test_tactic_allow_permits_matching_tactic(self):
        a = AbilityAllowlist(tactics=['discovery'])
        assert a.is_restrictive is True
        ok, reason = a.permits(StubAbility('x', 'discovery', 'T1083'))
        assert ok is True
        assert 'tactic discovery' in reason

    def test_tactic_allow_blocks_non_matching_tactic(self):
        a = AbilityAllowlist(tactics=['discovery'])
        ok, reason = a.permits(StubAbility('x', 'impact', 'T1485'))
        assert ok is False
        assert 'not in allowlist' in reason

    def test_ability_id_allow_permits_matching_id(self):
        a = AbilityAllowlist(ability_ids=['abcd'])
        ok, _ = a.permits(StubAbility('abcd', 'impact', 'T1485'))
        assert ok is True

    def test_technique_allow_permits_matching_technique(self):
        a = AbilityAllowlist(technique_ids=['T1083'])
        ok, _ = a.permits(StubAbility('x', 'impact', 'T1083'))
        assert ok is True

    def test_deny_ability_id_overrides_allow(self):
        a = AbilityAllowlist(tactics=['discovery'], deny_ability_ids=['bad'])
        ok, reason = a.permits(StubAbility('bad', 'discovery', 'T1083'))
        assert ok is False
        assert 'explicitly denied' in reason

    def test_deny_tactic_overrides_allow(self):
        a = AbilityAllowlist(ability_ids=['x'], deny_tactics=['impact'])
        ok, reason = a.permits(StubAbility('x', 'impact', 'T1'))
        assert ok is False
        assert 'tactic impact is explicitly denied' in reason

    def test_dict_input_works(self):
        a = AbilityAllowlist(tactics=['discovery'])
        ok, _ = a.permits({'ability_id': 'x', 'tactic': 'discovery', 'technique_id': 'T1'})
        assert ok is True
        ok, _ = a.permits({'ability_id': 'x', 'tactic': 'impact', 'technique_id': 'T1'})
        assert ok is False

    def test_tactic_case_insensitive(self):
        a = AbilityAllowlist(tactics=['Discovery'])
        ok, _ = a.permits(StubAbility('x', 'DISCOVERY', 'T1'))
        assert ok is True

    def test_from_config_handles_none(self):
        a = AbilityAllowlist.from_config(None)
        assert a.is_restrictive is False

    def test_from_config_builds_constraints(self):
        a = AbilityAllowlist.from_config({'tactics': ['discovery'], 'deny_tactics': ['impact']})
        assert 'discovery' in a.tactics
        assert 'impact' in a.deny_tactics

    def test_from_config_handles_all_keys(self):
        a = AbilityAllowlist.from_config({
            'ability_ids': ['a1'],
            'tactics': ['discovery'],
            'technique_ids': ['T1083'],
            'deny_ability_ids': ['bad'],
            'deny_tactics': ['impact'],
        })
        assert a.ability_ids == {'a1'}
        assert a.tactics == {'discovery'}
        assert a.technique_ids == {'T1083'}
        assert a.deny_ability_ids == {'bad'}
        assert a.deny_tactics == {'impact'}

    def test_deny_applies_even_in_permissive_mode(self):
        """Deny lists must work without positive constraints — otherwise a
        config with ONLY deny lists would be silently inert."""
        a = AbilityAllowlist(deny_tactics=['impact'])
        assert a.is_restrictive is False  # No positive constraints.
        ok, reason = a.permits(StubAbility('x', 'impact', 'T1'))
        assert ok is False
        assert 'tactic impact' in reason

    def test_deny_ability_id_applies_in_permissive_mode(self):
        a = AbilityAllowlist(deny_ability_ids=['bad'])
        ok, reason = a.permits(StubAbility('bad', 'discovery', 'T1'))
        assert ok is False
        assert 'explicitly denied' in reason

    def test_ability_without_tactic_still_evaluated(self):
        """Some abilities have no tactic — they must still be matchable by id/technique."""
        a = AbilityAllowlist(ability_ids=['x'])
        ok, _ = a.permits(StubAbility('x', None, None))
        assert ok is True

    def test_ability_without_id_or_tactic_denied_when_restrictive(self):
        a = AbilityAllowlist(tactics=['discovery'])
        ok, reason = a.permits(StubAbility(None, None, None))
        assert ok is False
        assert 'not in allowlist' in reason

    def test_dict_input_with_missing_keys(self):
        a = AbilityAllowlist(tactics=['discovery'])
        # Empty dict — neither permissive nor explicitly allowed.
        ok, _ = a.permits({})
        assert ok is False
        # Only ability_id provided.
        ok, _ = a.permits({'ability_id': 'x'})
        assert ok is False

    def test_deny_takes_precedence_over_explicit_allow(self):
        # If an ability_id is in BOTH allow and deny, deny must win.
        a = AbilityAllowlist(ability_ids=['x'], deny_ability_ids=['x'])
        ok, reason = a.permits(StubAbility('x', 'discovery', 'T1'))
        assert ok is False
        assert 'explicitly denied' in reason

    def test_technique_id_normalization_is_strict(self):
        """Unlike tactics, technique_ids are NOT lowercased — they're canonical
        identifiers (e.g. T1083). Verify the contract so a regression that
        lowercases them is caught."""
        a = AbilityAllowlist(technique_ids=['T1083'])
        ok, _ = a.permits(StubAbility('x', 'impact', 'T1083'))
        assert ok is True
        ok, _ = a.permits(StubAbility('x', 'impact', 't1083'))
        assert ok is False
