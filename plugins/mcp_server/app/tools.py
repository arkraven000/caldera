"""MCP tool implementations backed by Caldera's in-process services.

Each tool returns plain JSON-serializable data. Mutating tools (`approve_and_execute_link`)
go through the AbilityAllowlist + AuditLogger gate before touching any agent.
"""

import logging
from pathlib import Path

from app.ai_safety import (
    AbilityAllowlist,
    AuditLogger,
    compact_ability,
    compact_agent,
    compact_fact,
    compact_link,
)
from plugins.mcp_server.app.approval_tokens import ApprovalTokenStore


log = logging.getLogger(__name__)


class CalderaMCPTools:
    """Thin facade over Caldera's services. Constructed once at plugin enable() time."""

    def __init__(self, services, allowlist: AbilityAllowlist = None, audit_root: str = 'data/ai_audit',
                 require_approval: bool = True):
        self.services = services
        self.data_svc = services['data_svc']
        self.planning_svc = services['planning_svc']
        self.allowlist = allowlist or AbilityAllowlist()
        self.audit_root = Path(audit_root)
        self.require_approval = require_approval
        self.tokens = ApprovalTokenStore()

    async def list_operations(self) -> list:
        ops = await self.data_svc.locate('operations')
        return [{'id': o.id, 'name': o.name, 'state': getattr(o, 'state', None),
                 'planner': getattr(getattr(o, 'planner', None), 'name', None)} for o in ops]

    async def get_operation(self, operation_id: str) -> dict:
        ops = await self.data_svc.locate('operations', match=dict(id=operation_id))
        if not ops:
            return {'error': f'operation {operation_id} not found'}
        op = ops[0]
        chain = list(op.chain or [])
        return {
            'id': op.id,
            'name': op.name,
            'state': getattr(op, 'state', None),
            'adversary': getattr(getattr(op, 'adversary', None), 'name', None),
            'planner': getattr(getattr(op, 'planner', None), 'name', None),
            'agents': [compact_agent(a) for a in (op.agents or [])],
            'chain_length': len(chain),
            'recent_links': [compact_link(l) for l in chain[-15:]],
        }

    async def list_abilities(self, tactic: str = None, technique_id: str = None) -> list:
        abilities = await self.data_svc.locate('abilities')
        rows = []
        for a in abilities:
            if tactic and (getattr(a, 'tactic', None) or '').lower() != tactic.lower():
                continue
            if technique_id and getattr(a, 'technique_id', None) != technique_id:
                continue
            rows.append(compact_ability(a))
        return rows[:500]

    async def list_agents(self, operation_id: str = None) -> list:
        if operation_id:
            ops = await self.data_svc.locate('operations', match=dict(id=operation_id))
            if not ops:
                return []
            return [compact_agent(a) for a in (ops[0].agents or [])]
        agents = await self.data_svc.locate('agents')
        return [compact_agent(a) for a in agents]

    async def get_facts(self, operation_id: str) -> list:
        ops = await self.data_svc.locate('operations', match=dict(id=operation_id))
        if not ops:
            return []
        facts = []
        try:
            facts = await ops[0].all_facts()
        except Exception:
            facts = []
        return [compact_fact(f) for f in facts]

    async def propose_next_link(self, operation_id: str, ability_id: str, paw: str) -> dict:
        ops = await self.data_svc.locate('operations', match=dict(id=operation_id))
        if not ops:
            return {'error': f'operation {operation_id} not found'}
        op = ops[0]
        agent = next((a for a in (op.agents or []) if a.paw == paw), None)
        if not agent:
            return {'error': f'agent paw {paw} not attached to operation'}
        links = await self.planning_svc.get_links(operation=op, agent=agent)
        link = next((l for l in links if l.ability.ability_id == ability_id), None)
        if not link:
            return {'error': f'ability {ability_id} not currently runnable for {paw} '
                             f'(requirements unmet, wrong platform, or no executor)'}
        permitted, reason = self.allowlist.permits(link.ability)
        if self.allowlist.is_restrictive and not permitted:
            return {'error': f'denied by allowlist: {reason}'}
        token = self.tokens.mint(operation_id, ability_id, paw, link.id)
        audit = AuditLogger(operation_id, root=self.audit_root)
        await audit.record('mcp_propose', {'ability_id': ability_id, 'paw': paw,
                                           'link_id': link.id, 'token_issued': True})
        return {
            'link_id': link.id,
            'ability': compact_ability(link.ability),
            'paw': paw,
            'command_preview': getattr(link, 'plaintext_command', None) or getattr(link, 'command', '')[:300],
            'approval_token': token,
            'token_ttl_seconds': self.tokens.ttl,
            'allowlist_reason': reason,
        }

    async def approve_and_execute_link(self, operation_id: str, link_id: str,
                                       approval_token: str) -> dict:
        ok, msg = self.tokens.consume(approval_token, operation_id, link_id)
        audit = AuditLogger(operation_id, root=self.audit_root)
        if not ok:
            await audit.record('mcp_execute_denied', {'link_id': link_id, 'reason': msg})
            return {'error': msg}
        ops = await self.data_svc.locate('operations', match=dict(id=operation_id))
        if not ops:
            return {'error': f'operation {operation_id} not found'}
        op = ops[0]
        link = next((l for l in op.chain if l.id == link_id), None)
        if not link:
            link = await self._rebuild_link(op, link_id)
            if not link:
                return {'error': f'link {link_id} not found in operation chain'}
        await audit.record('mcp_execute', {'link_id': link_id, 'ability_id': link.ability.ability_id})
        applied_link_id = await op.apply(link)
        await op.wait_for_links_completion([applied_link_id])
        return {'link_id': applied_link_id, 'status': getattr(link, 'status', None)}

    async def summarize_operation(self, operation_id: str) -> dict:
        op_view = await self.get_operation(operation_id)
        facts = await self.get_facts(operation_id)
        return {
            **op_view,
            'facts_total': len(facts),
            'tactics_executed': sorted({l['tactic'] for l in op_view.get('recent_links', []) if l.get('tactic')}),
        }

    async def _rebuild_link(self, op, link_id: str):
        for agent in op.agents or []:
            links = await self.planning_svc.get_links(operation=op, agent=agent)
            for link in links:
                if link.id == link_id:
                    return link
        return None
