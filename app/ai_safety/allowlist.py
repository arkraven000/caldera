from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class AbilityAllowlist:
    """Filter Caldera abilities by id / tactic / technique with an optional deny list.

    Empty allow-fields mean "no restriction" — passing nothing yields a permissive allowlist,
    so callers MUST construct one with at least one positive constraint when running in auto mode.
    """

    ability_ids: set = field(default_factory=set)
    tactics: set = field(default_factory=set)
    technique_ids: set = field(default_factory=set)
    deny_ability_ids: set = field(default_factory=set)
    deny_tactics: set = field(default_factory=set)

    def __init__(self, ability_ids: Iterable[str] = None, tactics: Iterable[str] = None,
                 technique_ids: Iterable[str] = None, deny_ability_ids: Iterable[str] = None,
                 deny_tactics: Iterable[str] = None):
        self.ability_ids = {x for x in (ability_ids or [])}
        self.tactics = {x.lower() for x in (tactics or [])}
        self.technique_ids = {x for x in (technique_ids or [])}
        self.deny_ability_ids = {x for x in (deny_ability_ids or [])}
        self.deny_tactics = {x.lower() for x in (deny_tactics or [])}

    @property
    def is_restrictive(self) -> bool:
        return bool(self.ability_ids or self.tactics or self.technique_ids)

    def permits(self, ability) -> tuple:
        """Return (permitted, reason). ability is anything with .ability_id/.tactic/.technique_id."""
        if isinstance(ability, dict):
            ability_id = ability.get('ability_id')
            tactic = ability.get('tactic')
            technique_id = ability.get('technique_id')
        else:
            ability_id = getattr(ability, 'ability_id', None)
            tactic = getattr(ability, 'tactic', None)
            technique_id = getattr(ability, 'technique_id', None)
        if tactic:
            tactic = tactic.lower()

        if ability_id and ability_id in self.deny_ability_ids:
            return False, f'ability_id {ability_id} is explicitly denied'
        if tactic and tactic in self.deny_tactics:
            return False, f'tactic {tactic} is explicitly denied'

        if not self.is_restrictive:
            return True, 'allowlist is permissive (no positive constraints set)'

        if self.ability_ids and ability_id in self.ability_ids:
            return True, f'ability_id {ability_id} explicitly allowed'
        if self.tactics and tactic in self.tactics:
            return True, f'tactic {tactic} allowed'
        if self.technique_ids and technique_id in self.technique_ids:
            return True, f'technique_id {technique_id} allowed'

        return False, f'ability_id={ability_id} tactic={tactic} technique={technique_id} not in allowlist'

    @classmethod
    def from_config(cls, cfg: dict) -> 'AbilityAllowlist':
        cfg = cfg or {}
        return cls(
            ability_ids=cfg.get('ability_ids'),
            tactics=cfg.get('tactics'),
            technique_ids=cfg.get('technique_ids'),
            deny_ability_ids=cfg.get('deny_ability_ids'),
            deny_tactics=cfg.get('deny_tactics'),
        )
