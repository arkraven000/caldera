import ipaddress
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class TargetScope:
    """Restrict the AI to a subset of agents (by paw) and/or IP ranges."""

    paws: set = field(default_factory=set)
    cidrs: list = field(default_factory=list)

    def __init__(self, paws: Iterable[str] = None, cidrs: Iterable[str] = None):
        self.paws = {p for p in (paws or [])}
        self.cidrs = []
        for c in (cidrs or []):
            try:
                self.cidrs.append(ipaddress.ip_network(c, strict=False))
            except ValueError:
                continue

    @property
    def is_restrictive(self) -> bool:
        return bool(self.paws or self.cidrs)

    def permits_paw(self, paw: str) -> bool:
        if not self.is_restrictive:
            return True
        return paw in self.paws

    def permits_ip(self, ip: str) -> bool:
        if not self.cidrs:
            return True
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(addr in net for net in self.cidrs)

    @classmethod
    def from_config(cls, cfg: dict) -> 'TargetScope':
        cfg = cfg or {}
        return cls(paws=cfg.get('paws'), cidrs=cfg.get('cidrs'))
