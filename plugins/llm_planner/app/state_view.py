"""Compact JSON projection of an in-flight Operation for the LLM decision prompt.

We avoid sending the full Operation object — it contains executor bodies, encrypted
fact blobs, raw command output, etc. The model needs a summary tight enough to fit
in a few KB so the candidate-links block dominates the prompt budget.
"""

from app.ai_safety import compact_agent, compact_fact, compact_link


async def state_view(operation, max_chain: int = 25, max_facts: int = 80) -> dict:
    facts = []
    try:
        facts = await operation.all_facts()
    except Exception:
        facts = []
    chain = list(operation.chain or [])
    chain_view = []
    for link in chain[-max_chain:]:
        view = compact_link(link)
        view['status'] = getattr(link, 'status', None)
        view['finish'] = bool(getattr(link, 'finish', None))
        chain_view.append(view)
    return {
        'operation_id': getattr(operation, 'id', None),
        'name': getattr(operation, 'name', None),
        'adversary': getattr(getattr(operation, 'adversary', None), 'name', None),
        'state': getattr(operation, 'state', None),
        'agents': [compact_agent(a) for a in (operation.agents or [])],
        'chain_summary': {
            'total': len(chain),
            'recent': chain_view,
        },
        'facts_summary': {
            'total': len(facts),
            'sample': [compact_fact(f) for f in facts[:max_facts]],
        },
    }


def candidate_links_view(links) -> list:
    return [compact_link(l) for l in links]
