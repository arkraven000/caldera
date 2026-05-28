"""Shared JSONSchema tool definitions used by all three AI integration variations.

Keeping these in one place means the MCP server, the standalone client, and the
in-server planner all speak the same vocabulary — and changing a tool surface is
a single-file edit.
"""

CHOOSE_NEXT_LINK_TOOL = {
    'name': 'choose_next_link',
    'description': (
        'Choose the single next ability to execute for the current operation. '
        'Must select from the candidate list provided in the prompt. Returns reasoning '
        'and a confidence score so a human reviewer can audit the decision.'
    ),
    'input_schema': {
        'type': 'object',
        'properties': {
            'ability_id': {
                'type': 'string',
                'description': 'UUID of the ability to execute. MUST exist in the candidate list.',
            },
            'paw': {
                'type': 'string',
                'description': 'Paw (agent id) the ability should run on. MUST exist in the candidate list.',
            },
            'reasoning': {
                'type': 'string',
                'description': 'One-paragraph explanation of why this is the right next step given the operation state.',
            },
            'confidence': {
                'type': 'number',
                'minimum': 0.0,
                'maximum': 1.0,
                'description': '0..1 self-assessed confidence. Low confidence will be surfaced to the human reviewer.',
            },
            'expected_outcome': {
                'type': 'string',
                'description': 'What facts or state change you expect to result from this action.',
            },
        },
        'required': ['ability_id', 'reasoning', 'confidence'],
    },
}


STOP_OPERATION_TOOL = {
    'name': 'stop_operation',
    'description': 'Signal that the operation has met its objectives or has no productive next step. '
                   'Use this to terminate cleanly rather than burning the call budget.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'reason': {'type': 'string', 'description': 'Why the operation should stop.'},
        },
        'required': ['reason'],
    },
}


# Tool surface for the standalone client (Variation B). Each maps 1:1 to a method on
# CalderaClient and is sized to keep the operator's prompt under ~6k tokens before caching.
CALDERA_TOOL_SPECS = [
    {
        'name': 'list_abilities',
        'description': 'List ATT&CK abilities available to the operation, optionally filtered by tactic or technique id.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'tactic': {'type': 'string', 'description': 'discovery, collection, persistence, ...'},
                'technique_id': {'type': 'string', 'description': 'e.g. T1083'},
            },
        },
    },
    {
        'name': 'get_operation',
        'description': 'Get the full state of a single operation: agents, chain, facts, planner.',
        'input_schema': {
            'type': 'object',
            'properties': {'operation_id': {'type': 'string'}},
            'required': ['operation_id'],
        },
    },
    {
        'name': 'list_agents',
        'description': 'List deployed implants (agents) and their host/platform/privilege.',
        'input_schema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'get_facts',
        'description': 'List facts discovered/seeded for an operation. Facts feed ability template variables.',
        'input_schema': {
            'type': 'object',
            'properties': {'operation_id': {'type': 'string'}},
            'required': ['operation_id'],
        },
    },
    {
        'name': 'add_fact',
        'description': 'Seed a fact into an operation. Use sparingly — prefer letting parsers discover facts.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'operation_id': {'type': 'string'},
                'trait': {'type': 'string', 'description': 'e.g. host.user.name'},
                'value': {'type': 'string'},
            },
            'required': ['operation_id', 'trait', 'value'],
        },
    },
    {
        'name': 'propose_link',
        'description': 'Build a potential link for an operation WITHOUT executing it. Returns the link payload for review.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'operation_id': {'type': 'string'},
                'ability_id': {'type': 'string'},
                'paw': {'type': 'string'},
            },
            'required': ['operation_id', 'ability_id', 'paw'],
        },
    },
    {
        'name': 'execute_link',
        'description': 'Execute a previously proposed link. NOOP in dry-run mode. Returns the live link id.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'operation_id': {'type': 'string'},
                'link_payload': {'type': 'object', 'description': 'The payload returned from propose_link.'},
            },
            'required': ['operation_id', 'link_payload'],
        },
    },
    {
        'name': 'wait_for_link',
        'description': 'Block until a previously executed link completes (or times out), then return its result/output/facts.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'operation_id': {'type': 'string'},
                'link_id': {'type': 'string'},
                'timeout_seconds': {'type': 'integer', 'default': 120},
            },
            'required': ['operation_id', 'link_id'],
        },
    },
    {
        'name': 'pause_operation',
        'description': 'Pause an operation so the external agent can drive it without racing the server-side planner.',
        'input_schema': {
            'type': 'object',
            'properties': {'operation_id': {'type': 'string'}},
            'required': ['operation_id'],
        },
    },
    {
        'name': 'resume_operation',
        'description': 'Resume a paused operation.',
        'input_schema': {
            'type': 'object',
            'properties': {'operation_id': {'type': 'string'}},
            'required': ['operation_id'],
        },
    },
    {
        'name': 'summarize',
        'description': 'Provide a natural-language summary of operation progress for the operator. No state change.',
        'input_schema': {
            'type': 'object',
            'properties': {'operation_id': {'type': 'string'}, 'audience': {'type': 'string', 'enum': ['operator', 'executive', 'blue_team']}},
            'required': ['operation_id'],
        },
    },
    STOP_OPERATION_TOOL,
]
