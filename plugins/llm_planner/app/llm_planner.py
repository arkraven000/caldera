"""LogicalPlanner that delegates per-tick decisions to Anthropic Claude.

Wire-up follows the standard Caldera planner contract (see app/planners/atomic.py):
- Class name MUST be LogicalPlanner
- Constructor receives (operation, planning_svc, stopping_conditions, **params)
- async execute() drives planning_svc.execute_planner(self)
- self.next_bucket / self.state_machine drive bucket transitions
- self.stopping_condition_met halts the planner

Safety posture:
- dry_run=True by default. Discarded links never reach an agent.
- AbilityAllowlist is applied to candidate links BEFORE the prompt — the model never
  sees a disallowed ability.
- max_calls caps Anthropic spend per operation. On API failure the planner fails closed.
"""

import logging
from pathlib import Path

from app.ai_safety import AbilityAllowlist, AuditLogger, MODEL_STEP, get_async_client
from app.ai_safety.anthropic_client import AnthropicNotConfigured
from plugins.llm_planner.app.decision import decide


log = logging.getLogger(__name__)


class LogicalPlanner:

    def __init__(self, operation, planning_svc, stopping_conditions=(),
                 model: str = MODEL_STEP, max_calls: int = 30, dry_run: bool = True,
                 allowlist_tactics=None, allowlist_ability_ids=None,
                 allowlist_technique_ids=None, deny_tactics=None,
                 audit_dir: str = 'data/ai_audit', max_tokens: int = 1024):
        self.operation = operation
        self.planning_svc = planning_svc
        self.stopping_conditions = stopping_conditions
        self.stopping_condition_met = False
        self.state_machine = ['llm_step']
        self.next_bucket = 'llm_step'

        self.model = model
        self.max_calls = int(max_calls)
        self.dry_run = bool(dry_run)
        self.max_tokens = int(max_tokens)
        self.deny_tactics = list(deny_tactics or [])
        self.allowlist = AbilityAllowlist(
            ability_ids=allowlist_ability_ids,
            tactics=allowlist_tactics,
            technique_ids=allowlist_technique_ids,
            deny_tactics=deny_tactics,
        )
        self.audit = AuditLogger(operation.id, root=Path(audit_dir))
        self.calls = 0
        try:
            self.client = get_async_client()
        except AnthropicNotConfigured as exc:
            log.error('llm_planner disabled: %s', exc)
            self.client = None
            self.next_bucket = None

    async def execute(self):
        if self.client is None:
            return
        await self.audit.record('planner_start', {
            'model': self.model,
            'max_calls': self.max_calls,
            'dry_run': self.dry_run,
            'allowlist_tactics': sorted(self.allowlist.tactics),
            'allowlist_ability_ids': sorted(self.allowlist.ability_ids),
            'deny_tactics': self.deny_tactics,
        })
        await self.planning_svc.execute_planner(self)
        await self.audit.record('planner_end', {'calls': self.calls})

    async def llm_step(self):
        if self.calls >= self.max_calls:
            await self.audit.record('halt', {'reason': 'max_calls_reached', 'calls': self.calls})
            self.next_bucket = None
            return

        links = await self.planning_svc.get_links(operation=self.operation, agent=None)
        if not links:
            await self.audit.record('halt', {'reason': 'no_candidate_links'})
            self.next_bucket = None
            return

        permitted = []
        denied = []
        for link in links:
            ok, reason = self.allowlist.permits(link.ability)
            (permitted if ok else denied).append((link, reason))

        if denied:
            await self.audit.record('filtered', {
                'denied_count': len(denied),
                'sample': [{'ability_id': l.ability.ability_id, 'reason': r} for l, r in denied[:5]],
            })
        if not permitted:
            await self.audit.record('halt', {'reason': 'no_permitted_links_after_allowlist',
                                             'total_candidates': len(links)})
            self.next_bucket = None
            return

        try:
            decision = await decide(
                self.client, self.operation, [l for l, _ in permitted],
                model=self.model, max_tokens=self.max_tokens,
                denied_tactics=self.deny_tactics,
            )
        except Exception as exc:
            log.exception('llm_planner: decide() failed: %s', exc)
            await self.audit.record('halt', {'reason': 'decide_exception', 'error': str(exc)})
            self.next_bucket = None
            return

        self.calls += 1
        ability_id = decision.get('ability_id')
        await self.audit.record('decision', {**decision, 'call_index': self.calls})

        chosen = next(
            (l for l, _ in permitted if l.ability.ability_id == ability_id),
            None,
        )
        if chosen is None:
            await self.audit.record('halt', {
                'reason': 'model_chose_unknown_ability',
                'ability_id': ability_id,
            })
            self.next_bucket = None
            return

        if self.dry_run:
            chosen.status = chosen.states.get('DISCARD', -2)
            self.operation.add_link(chosen)
            await self.audit.record('executed_dry_run', {
                'link_id': chosen.id, 'ability_id': ability_id, 'paw': chosen.paw,
            })
            return

        link_id = await self.operation.apply(chosen)
        await self.audit.record('executed_live', {
            'link_id': link_id, 'ability_id': ability_id, 'paw': chosen.paw,
        })
        await self.operation.wait_for_links_completion([link_id])
