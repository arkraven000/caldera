import argparse
import logging
import os
import sys

from app.ai_safety import AbilityAllowlist
from tools.claude_agent.agent_loop import run
from tools.claude_agent.caldera_client import CalderaClient


def _parse_allowlist(arg: str) -> AbilityAllowlist:
    """Parse a comma-separated allowlist spec: tactics=a,b;ability_ids=x,y;technique_ids=T1083"""
    spec = {}
    if not arg:
        return AbilityAllowlist()
    for part in arg.split(';'):
        if '=' not in part:
            continue
        key, value = part.split('=', 1)
        spec[key.strip()] = [v.strip() for v in value.split(',') if v.strip()]
    return AbilityAllowlist(
        ability_ids=spec.get('ability_ids'),
        tactics=spec.get('tactics'),
        technique_ids=spec.get('technique_ids'),
        deny_ability_ids=spec.get('deny_ability_ids'),
        deny_tactics=spec.get('deny_tactics'),
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='python -m tools.claude_agent',
        description='Drive a Caldera operation with Anthropic Claude via the Caldera REST API.',
    )
    p.add_argument('--server', default=os.environ.get('CALDERA_URL', 'http://127.0.0.1:8888'),
                   help='Caldera base URL (default: $CALDERA_URL or http://127.0.0.1:8888)')
    p.add_argument('--api-key', default=os.environ.get('CALDERA_API_KEY'),
                   help='Caldera API key (default: $CALDERA_API_KEY).')
    p.add_argument('--operation', required=True, help='Operation id to drive.')
    p.add_argument('--goal', required=True, help='Operator objective in plain English.')
    p.add_argument('--mode', choices=['dry-run', 'interactive', 'auto'], default='dry-run',
                   help='dry-run (default): no mutations. interactive: prompt y/N/e per mutation. auto: requires --allowlist.')
    p.add_argument('--allowlist', default='',
                   help='Allowlist spec, e.g. "tactics=discovery,collection;deny_tactics=impact".')
    p.add_argument('--model', default='claude-sonnet-4-7')
    p.add_argument('--max-steps', type=int, default=20)
    p.add_argument('--max-tokens', type=int, default=4096)
    p.add_argument('--audit-dir', default=os.path.expanduser('~/.caldera_ai/audit'))
    p.add_argument('--verbose', action='store_true')
    return p


async def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    if not args.api_key:
        print('error: --api-key (or $CALDERA_API_KEY) is required', file=sys.stderr)
        return 2
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('error: ANTHROPIC_API_KEY env var is required', file=sys.stderr)
        return 2

    allowlist = _parse_allowlist(args.allowlist)
    if args.mode == 'auto' and not allowlist.is_restrictive:
        print('error: --mode auto requires --allowlist with at least one positive constraint', file=sys.stderr)
        return 2

    async with CalderaClient(args.server, args.api_key) as caldera:
        summary = await run(
            caldera_client=caldera,
            operation_id=args.operation,
            goal=args.goal,
            mode=args.mode,
            model=args.model,
            max_steps=args.max_steps,
            max_tokens=args.max_tokens,
            allowlist=allowlist,
            audit_dir=args.audit_dir,
        )
    print('--- session summary ---')
    for k, v in summary.items():
        print(f'{k}: {v}')
    return 0
