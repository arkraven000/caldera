"""Anthropic call that returns the planner's next-link decision.

Single round-trip per planner tick. `tool_choice` is forced to `choose_next_link`
so the model MUST emit a structured decision — no free-text actions reach the planner.
"""

import json
import logging

from app.ai_safety import CHOOSE_NEXT_LINK_TOOL, MODEL_STEP
from app.ai_safety.anthropic_client import cache_block
from plugins.llm_planner.app.state_view import candidate_links_view, state_view


log = logging.getLogger(__name__)


PLANNER_SYSTEM = (
    "You are the decision engine for a Caldera adversary-emulation planner running in an "
    "authorized lab environment. On each tick you receive a compact view of the operation "
    "state and a list of candidate abilities that are *already validated* (requirements met, "
    "agent matched). Choose exactly ONE candidate that best advances the operation toward "
    "useful discovery and reconnaissance while respecting the listed denied tactics. "
    "Prefer reconnaissance and collection before any state change. If no candidate is a "
    "productive step, choose the one with the most diagnostic value (e.g. lowest-risk discovery). "
    "Always emit `confidence`; a low confidence will be surfaced to the human reviewer."
)


async def decide(client, operation, links, model: str = MODEL_STEP, max_tokens: int = 1024,
                 denied_tactics=None) -> dict:
    """Return {'ability_id': ..., 'paw': ..., 'reasoning': ..., 'confidence': ...}.

    Raises if the model fails to emit a tool_use block (the forced tool_choice should
    prevent this, but we re-raise so the planner can fail closed).
    """
    state = await state_view(operation)
    candidates = candidate_links_view(links)
    denied_tactics = denied_tactics or []

    user_content = [
        cache_block('CANDIDATE LINKS (validated, choose exactly one ability_id from this list):\n'
                    + json.dumps(candidates, default=str)),
        {'type': 'text', 'text': json.dumps({
            'denied_tactics': denied_tactics,
            'operation_state': state,
        }, default=str)},
    ]

    resp = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[cache_block(PLANNER_SYSTEM)],
        tools=[CHOOSE_NEXT_LINK_TOOL],
        tool_choice={'type': 'tool', 'name': 'choose_next_link'},
        messages=[{'role': 'user', 'content': user_content}],
    )

    for block in resp.content:
        if getattr(block, 'type', None) == 'tool_use' and block.name == 'choose_next_link':
            decision = dict(block.input or {})
            decision['_usage'] = {
                'input_tokens': getattr(resp.usage, 'input_tokens', 0),
                'output_tokens': getattr(resp.usage, 'output_tokens', 0),
                'cache_read_input_tokens': getattr(resp.usage, 'cache_read_input_tokens', 0),
                'cache_creation_input_tokens': getattr(resp.usage, 'cache_creation_input_tokens', 0),
            }
            return decision

    raise RuntimeError('llm_planner: model returned no choose_next_link tool_use block')
