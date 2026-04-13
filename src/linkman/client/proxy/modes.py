"""
Proxy mode management for routing decisions.

Provides:
- Global mode (all traffic through proxy)
- Rule-based mode (selective proxy)
- Direct mode (no proxy)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Self

from linkman.shared.protocol.types import Address
from linkman.shared.utils.logger import get_logger
from linkman.client.rules.matcher import RuleMatcher

logger = get_logger("client.modes")


class ProxyMode(Enum):
    """Proxy operation modes."""

    GLOBAL = "global"
    RULES = "rules"
    DIRECT = "direct"


@dataclass
class ModeStats:
    """Statistics for mode usage."""

    proxied_requests: int = 0
    direct_requests: int = 0
    blocked_requests: int = 0


class ModeManager:
    """
    Manages proxy modes and routing decisions.

    Modes:
    - GLOBAL: All traffic goes through proxy
    - RULES: Traffic routed based on rules
    - DIRECT: All traffic goes direct (no proxy)
    """

    def __init__(
        self,
        mode: ProxyMode = ProxyMode.RULES,
        rule_matcher: RuleMatcher | None = None,
    ):
        """
        Initialize mode manager.

        Args:
            mode: Initial proxy mode
            rule_matcher: Rule matcher for RULES mode
        """
        self._mode = mode
        self._rule_matcher = rule_matcher or RuleMatcher()
        self._stats = ModeStats()
        self._on_mode_change: callable | None = None

    @property
    def mode(self) -> ProxyMode:
        """Get current mode."""
        return self._mode

    @property
    def stats(self) -> ModeStats:
        """Get mode statistics."""
        return self._stats

    def set_mode(self, mode: ProxyMode) -> None:
        """Set proxy mode."""
        if mode != self._mode:
            logger.info(f"Mode changed: {self._mode.value} -> {mode.value}")
            self._mode = mode
            if self._on_mode_change:
                self._on_mode_change(mode)

    def set_mode_callback(self, callback: callable) -> None:
        """Set callback for mode changes."""
        self._on_mode_change = callback

    async def should_proxy(self, target: Address) -> bool:
        """
        Determine if target should go through proxy.

        Args:
            target: Target address

        Returns:
            True if should use proxy
        """
        if self._mode == ProxyMode.GLOBAL:
            self._stats.proxied_requests += 1
            return True

        if self._mode == ProxyMode.DIRECT:
            self._stats.direct_requests += 1
            return False

        result = self._rule_matcher.match(target)

        if result.is_proxy:
            self._stats.proxied_requests += 1
        elif result.is_block:
            self._stats.blocked_requests += 1
        else:
            self._stats.direct_requests += 1

        return result.is_proxy

    def add_rule(self, pattern: str, is_proxy: bool = True) -> None:
        """Add a routing rule."""
        self._rule_matcher.add_rule(pattern, is_proxy)

    def remove_rule(self, pattern: str) -> None:
        """Remove a routing rule."""
        self._rule_matcher.remove_rule(pattern)

    def load_rules(self, rules: list[dict]) -> None:
        """Load rules from list."""
        self._rule_matcher.load_rules(rules)

    def get_rules(self) -> list[dict]:
        """Get all rules."""
        return self._rule_matcher.get_rules()

    def get_stats_dict(self) -> dict:
        """Get statistics as dictionary."""
        return {
            "mode": self._mode.value,
            "proxied_requests": self._stats.proxied_requests,
            "direct_requests": self._stats.direct_requests,
            "blocked_requests": self._stats.blocked_requests,
            "total_rules": len(self._rule_matcher.get_rules()),
        }

    @classmethod
    def from_config(cls, config: dict) -> Self:
        """Create from configuration."""
        mode = ProxyMode(config.get("mode", "rules"))

        matcher = RuleMatcher()
        if "rules" in config:
            matcher.load_rules(config["rules"])

        return cls(mode=mode, rule_matcher=matcher)
