"""
Rule matching for proxy routing decisions.

Provides:
- Domain matching
- IP/CIDR matching
- Port matching
- Rule prioritization
"""

from __future__ import annotations

import fnmatch
import ipaddress
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Self


class RuleType(Enum):
    """Rule types."""

    DOMAIN = "domain"
    DOMAIN_SUFFIX = "domain_suffix"
    DOMAIN_KEYWORD = "domain_keyword"
    IP_CIDR = "ip_cidr"
    PORT = "port"
    GEOSITE = "geosite"
    FINAL = "final"


class RuleAction(Enum):
    """Rule actions."""

    PROXY = "proxy"
    DIRECT = "direct"
    BLOCK = "block"


@dataclass
class Rule:
    """A routing rule."""

    type: RuleType
    pattern: str
    action: RuleAction = RuleAction.PROXY
    priority: int = 0

    def matches(self, target_host: str, target_port: int) -> bool:
        """Check if target matches this rule."""
        if self.type == RuleType.DOMAIN:
            return target_host.lower() == self.pattern.lower()

        if self.type == RuleType.DOMAIN_SUFFIX:
            return target_host.lower().endswith(self.pattern.lower())

        if self.type == RuleType.DOMAIN_KEYWORD:
            return self.pattern.lower() in target_host.lower()

        if self.type == RuleType.IP_CIDR:
            try:
                ip = ipaddress.ip_address(target_host)
                network = ipaddress.ip_network(self.pattern, strict=False)
                return ip in network
            except ValueError:
                return False

        if self.type == RuleType.PORT:
            if "-" in self.pattern:
                start, end = map(int, self.pattern.split("-"))
                return start <= target_port <= end
            return target_port == int(self.pattern)

        if self.type == RuleType.FINAL:
            return True

        return False


@dataclass
class MatchResult:
    """Result of rule matching."""

    matched: bool = False
    is_proxy: bool = False
    is_direct: bool = False
    is_block: bool = False
    rule: Rule | None = None


class RuleMatcher:
    """
    Matches targets against routing rules.

    Rules are evaluated in priority order:
    1. Higher priority rules first
    2. First matching rule wins
    3. Default action is DIRECT
    """

    DEFAULT_RULES = [
        {"type": "domain_suffix", "pattern": "google.com", "action": "proxy"},
        {"type": "domain_suffix", "pattern": "youtube.com", "action": "proxy"},
        {"type": "domain_suffix", "pattern": "github.com", "action": "proxy"},
        {"type": "domain_suffix", "pattern": "githubusercontent.com", "action": "proxy"},
        {"type": "domain_keyword", "pattern": "google", "action": "proxy"},
        {"type": "ip_cidr", "pattern": "10.0.0.0/8", "action": "direct"},
        {"type": "ip_cidr", "pattern": "172.16.0.0/12", "action": "direct"},
        {"type": "ip_cidr", "pattern": "192.168.0.0/16", "action": "direct"},
        {"type": "ip_cidr", "pattern": "127.0.0.0/8", "action": "direct"},
        {"type": "final", "pattern": "", "action": "direct"},
    ]

    def __init__(self):
        """Initialize rule matcher."""
        self._rules: list[Rule] = []
        self._load_default_rules()

    def _load_default_rules(self) -> None:
        """Load default rules."""
        for rule_config in self.DEFAULT_RULES:
            self.add_rule(
                pattern=rule_config["pattern"],
                is_proxy=rule_config["action"] == "proxy",
                rule_type=rule_config["type"],
            )

    def add_rule(
        self,
        pattern: str,
        is_proxy: bool = True,
        rule_type: str = "domain_suffix",
        priority: int = 0,
    ) -> None:
        """
        Add a routing rule.

        Args:
            pattern: Rule pattern
            is_proxy: True for proxy, False for direct
            rule_type: Type of rule
            priority: Rule priority (higher = checked first)
        """
        try:
            rtype = RuleType(rule_type)
        except ValueError:
            rtype = RuleType.DOMAIN_SUFFIX

        action = RuleAction.PROXY if is_proxy else RuleAction.DIRECT

        rule = Rule(
            type=rtype,
            pattern=pattern,
            action=action,
            priority=priority,
        )

        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, pattern: str) -> bool:
        """
        Remove a rule by pattern.

        Args:
            pattern: Rule pattern to remove

        Returns:
            True if rule was removed
        """
        for i, rule in enumerate(self._rules):
            if rule.pattern == pattern:
                del self._rules[i]
                return True
        return False

    def match(self, target) -> MatchResult:
        """
        Match target against rules.

        Args:
            target: Target address (Address type)

        Returns:
            MatchResult
        """
        from linkman.shared.protocol.types import Address

        if not isinstance(target, Address):
            return MatchResult(matched=False, is_direct=True)

        host = target.host
        port = target.port

        for rule in self._rules:
            if rule.matches(host, port):
                result = MatchResult(
                    matched=True,
                    rule=rule,
                )

                if rule.action == RuleAction.PROXY:
                    result.is_proxy = True
                elif rule.action == RuleAction.DIRECT:
                    result.is_direct = True
                elif rule.action == RuleAction.BLOCK:
                    result.is_block = True

                return result

        return MatchResult(matched=False, is_direct=True)

    def load_rules(self, rules: list[dict]) -> None:
        """
        Load rules from configuration.

        Args:
            rules: List of rule configurations
        """
        self._rules.clear()

        for i, rule_config in enumerate(rules):
            self.add_rule(
                pattern=rule_config.get("pattern", ""),
                is_proxy=rule_config.get("action", "proxy") == "proxy",
                rule_type=rule_config.get("type", "domain_suffix"),
                priority=rule_config.get("priority", 1000 - i),
            )

    def get_rules(self) -> list[dict]:
        """Get all rules as dictionaries."""
        return [
            {
                "type": rule.type.value,
                "pattern": rule.pattern,
                "action": rule.action.value,
                "priority": rule.priority,
            }
            for rule in self._rules
        ]

    def clear_rules(self) -> None:
        """Clear all rules."""
        self._rules.clear()

    @classmethod
    def from_config(cls, config: dict) -> Self:
        """Create from configuration."""
        matcher = cls()
        if "rules" in config:
            matcher.load_rules(config["rules"])
        return matcher
