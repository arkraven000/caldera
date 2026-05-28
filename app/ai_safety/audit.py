import json
import os
import time
from pathlib import Path


class AuditLogger:
    """JSONL audit log keyed by operation id.

    Every AI decision and tool invocation is appended as a single JSON line so the
    log is replayable, tail-able, and survives process restart. Writes are best-effort
    and never raise into the planner loop.
    """

    def __init__(self, operation_id: str, root: Path = None):
        self.operation_id = operation_id
        self.root = Path(root) if root else Path('data/ai_audit')
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.path = self.root / f'{operation_id}.jsonl'

    async def record(self, event: str, payload: dict, decided_by: str = 'claude') -> None:
        row = {
            'ts': time.time(),
            'operation_id': self.operation_id,
            'event': event,
            'decided_by': decided_by,
            'pid': os.getpid(),
            'payload': payload,
        }
        try:
            with self.path.open('a', encoding='utf-8') as fh:
                fh.write(json.dumps(row, default=str) + '\n')
        except OSError:
            pass

    def record_sync(self, event: str, payload: dict, decided_by: str = 'claude') -> None:
        row = {
            'ts': time.time(),
            'operation_id': self.operation_id,
            'event': event,
            'decided_by': decided_by,
            'pid': os.getpid(),
            'payload': payload,
        }
        try:
            with self.path.open('a', encoding='utf-8') as fh:
                fh.write(json.dumps(row, default=str) + '\n')
        except OSError:
            pass
