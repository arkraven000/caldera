"""Thin factory for the Anthropic async client.

We deliberately do NOT pin a specific SDK version here — the SDK is an optional
dependency only required when an AI variation is actually enabled. The factory raises
a clean error if anthropic is not installed or the API key is missing.
"""

import os
from pathlib import Path

MODEL_PLAN = 'claude-opus-4-7'
MODEL_STEP = 'claude-sonnet-4-7'
DEFAULT_MAX_TOKENS = 4096

_BRIEF_PATH = Path(__file__).parent / 'agent_brief.md'
_brief_cache: str = None


class AnthropicNotConfigured(RuntimeError):
    pass


def get_async_client(api_key: str = None):
    """Return an anthropic.AsyncAnthropic client. Raises AnthropicNotConfigured on misconfig."""
    try:
        import anthropic  # type: ignore
    except ImportError as exc:
        raise AnthropicNotConfigured(
            'The anthropic SDK is not installed. Run `pip install anthropic` to enable AI integrations.'
        ) from exc

    key = api_key or os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        raise AnthropicNotConfigured(
            'ANTHROPIC_API_KEY is not set. Export it in the environment or pass api_key=... to get_async_client().'
        )
    return anthropic.AsyncAnthropic(api_key=key)


def cache_block(text: str) -> dict:
    """Build a prompt-cacheable text block. Use for the system prompt and large
    static blocks (ability catalog, adversary profile) that repeat across requests.
    """
    return {'type': 'text', 'text': text, 'cache_control': {'type': 'ephemeral'}}


def load_agent_brief() -> str:
    """Return the contents of agent_brief.md, the cached red-team grounding doc
    that every AI variation prepends to its system prompt.

    Read once and memoized — the file is ~7 kB and the path is fixed. If the
    file is missing (e.g. someone removed it), return empty string rather than
    raising: the planner loop runs degraded but functional, and a missing
    brief is a deployment issue, not a model-driven failure mode.
    """
    global _brief_cache
    if _brief_cache is not None:
        return _brief_cache
    try:
        _brief_cache = _BRIEF_PATH.read_text(encoding='utf-8')
    except OSError:
        _brief_cache = ''
    return _brief_cache
