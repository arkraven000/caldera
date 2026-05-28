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
