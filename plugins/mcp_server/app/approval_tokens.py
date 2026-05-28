"""Single-use approval tokens.

`propose_next_link` mints a token bound to (operation_id, ability_id, paw) with a
short TTL. `approve_and_execute_link` MUST present a valid token before the link
runs against an agent. Tokens are in-memory only — process restart invalidates them.
"""

import secrets
import time
from dataclasses import dataclass


@dataclass
class _TokenEntry:
    token: str
    operation_id: str
    ability_id: str
    paw: str
    link_id: str
    expires_at: float


class ApprovalTokenStore:

    def __init__(self, ttl_seconds: int = 60):
        self.ttl = ttl_seconds
        self._tokens: dict = {}

    def mint(self, operation_id: str, ability_id: str, paw: str, link_id: str) -> str:
        self._gc()
        token = secrets.token_urlsafe(24)
        self._tokens[token] = _TokenEntry(
            token=token, operation_id=operation_id, ability_id=ability_id,
            paw=paw, link_id=link_id, expires_at=time.time() + self.ttl,
        )
        return token

    def consume(self, token: str, operation_id: str, link_id: str) -> tuple:
        """Return (ok, message). Token is removed on success or on hard failure."""
        self._gc()
        entry = self._tokens.get(token)
        if not entry:
            return False, 'unknown or expired approval token'
        if entry.operation_id != operation_id:
            self._tokens.pop(token, None)
            return False, 'token does not match operation id'
        if entry.link_id != link_id:
            return False, 'token does not match link id'
        self._tokens.pop(token, None)
        return True, 'approved'

    def _gc(self):
        now = time.time()
        expired = [t for t, e in self._tokens.items() if e.expires_at < now]
        for t in expired:
            self._tokens.pop(t, None)
