"""Operator approval gate.

In interactive mode, every mutating tool call is shown to the operator before it runs.
We deliberately avoid third-party TUI libraries here so the tool runs anywhere with stock Python.
"""

import json
import sys


MUTATING_TOOLS = {'execute_link', 'add_fact', 'pause_operation', 'resume_operation'}


def needs_approval(tool_name: str, mode: str) -> bool:
    if mode == 'auto':
        return False
    if mode == 'dry-run':
        return False
    return tool_name in MUTATING_TOOLS


def prompt_operator(tool_name: str, tool_input: dict) -> tuple:
    """Return (approved: bool, edited_input: dict | None, message: str)."""
    print('\n----- AI ACTION REQUEST -----', file=sys.stderr)
    print(f'tool: {tool_name}', file=sys.stderr)
    print(f'input: {json.dumps(tool_input, indent=2)}', file=sys.stderr)
    print('Approve? [y]es / [N]o / [e]dit input: ', end='', file=sys.stderr, flush=True)
    try:
        choice = sys.stdin.readline().strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False, None, 'operator aborted (no input)'
    if choice in ('y', 'yes'):
        return True, tool_input, 'approved'
    if choice in ('e', 'edit'):
        print('Paste new JSON input (single line) or empty to keep:', file=sys.stderr, flush=True)
        line = sys.stdin.readline().strip()
        if not line:
            return True, tool_input, 'approved unchanged'
        try:
            new_input = json.loads(line)
        except json.JSONDecodeError as exc:
            return False, None, f'invalid JSON: {exc}'
        return True, new_input, 'approved with edits'
    return False, None, 'operator declined'
