"""Compact JSON projections of Caldera objects for LLM prompts.

Full ability/link/operation objects contain executor bodies, payloads, full requirement
trees etc. — too large to fit in a prompt at scale, and most of it is noise for a
decision. These helpers project the *minimum* the model needs to make a sensible pick.
"""


def compact_ability(ability) -> dict:
    return {
        'ability_id': getattr(ability, 'ability_id', None),
        'name': getattr(ability, 'name', None),
        'tactic': getattr(ability, 'tactic', None),
        'technique_id': getattr(ability, 'technique_id', None),
        'technique_name': getattr(ability, 'technique_name', None),
        'description': (getattr(ability, 'description', '') or '')[:300],
        'platforms': sorted({getattr(e, 'platform', None) for e in (getattr(ability, 'executors', []) or []) if getattr(e, 'platform', None)}),
    }


def compact_link(link) -> dict:
    ability = getattr(link, 'ability', None)
    return {
        'link_id': getattr(link, 'id', None),
        'paw': getattr(link, 'paw', None),
        'ability_id': getattr(ability, 'ability_id', None),
        'ability_name': getattr(ability, 'name', None),
        'tactic': getattr(ability, 'tactic', None),
        'technique_id': getattr(ability, 'technique_id', None),
        'score': getattr(link, 'score', 0),
        'platform': getattr(getattr(link, 'executor', None), 'platform', None),
    }


def compact_fact(fact) -> dict:
    return {
        'trait': getattr(fact, 'trait', None),
        'value': getattr(fact, 'value', None),
        'score': getattr(fact, 'score', None),
        'source': getattr(fact, 'source', None),
    }


def compact_agent(agent) -> dict:
    return {
        'paw': getattr(agent, 'paw', None),
        'host': getattr(agent, 'host', None),
        'platform': getattr(agent, 'platform', None),
        'username': getattr(agent, 'username', None),
        'privilege': getattr(agent, 'privilege', None),
        'trusted': getattr(agent, 'trusted', None),
        'last_seen': str(getattr(agent, 'last_seen', '')),
    }


async def build_ability_catalog(data_svc, tactic: str = None, technique_id: str = None) -> list:
    """Materialize the abilities catalog as a list of compact dicts.

    Designed to be cached in the LLM context (the catalog rarely changes within a session).
    """
    abilities = await data_svc.locate('abilities')
    rows = []
    for a in abilities:
        if tactic and (getattr(a, 'tactic', None) or '').lower() != tactic.lower():
            continue
        if technique_id and getattr(a, 'technique_id', None) != technique_id:
            continue
        rows.append(compact_ability(a))
    rows.sort(key=lambda r: ((r.get('tactic') or ''), (r.get('name') or '')))
    return rows
