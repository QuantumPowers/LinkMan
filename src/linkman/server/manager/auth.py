"""
Authentication and access control.

Provides:
- Identity verification
- Access rules
- IP-based restrictions
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Self

from linkman.shared.protocol.types import Address
from linkman.shared.utils.logger import get_logger

logger = get_logger("server.auth")


@dataclass
class AccessRule:
    """Access control rule."""

    name: str
    allowed: bool = True
    networks: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)

    def matches(self, target: Address) -> bool:
        """Check if target matches this rule."""
        if self.ports and target.port not in self.ports:
            return False

        if self.domains and target.is_domain:
            for domain in self.domains:
                if target.host.endswith(domain):
                    return True
            return False

        if self.networks and not target.is_domain:
            try:
                target_ip = ipaddress.ip_address(target.host)
                for network in self.networks:
                    if target_ip in ipaddress.ip_network(network, strict=False):
                        return True
                return False
            except ValueError:
                return False

        return True


class AuthManager:
    """
    Manages authentication and access control.

    Features:
    - Identity-based authentication
    - IP whitelist/blacklist
    - Target access rules
    """

    def __init__(
        self,
        allowed_identities: list[str] | None = None,
        ip_whitelist: list[str] | None = None,
        ip_blacklist: list[str] | None = None,
        access_rules: list[AccessRule] | None = None,
        default_allow: bool = True,
    ):
        """
        Initialize auth manager.

        Args:
            allowed_identities: List of allowed identity strings
            ip_whitelist: List of allowed IP networks
            ip_blacklist: List of blocked IP networks
            access_rules: List of access rules
            default_allow: Default allow policy
        """
        self._allowed_identities = set(allowed_identities or [])
        self._ip_whitelist = self._parse_networks(ip_whitelist or [])
        self._ip_blacklist = self._parse_networks(ip_blacklist or [])
        self._access_rules = access_rules or []
        self._default_allow = default_allow

    @staticmethod
    def _parse_networks(networks: list[str]) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        """Parse network strings to network objects."""
        result = []
        for net in networks:
            try:
                result.append(ipaddress.ip_network(net, strict=False))
            except ValueError:
                logger.warning(f"Invalid network: {net}")
        return result

    def add_identity(self, identity: str) -> None:
        """Add an allowed identity."""
        self._allowed_identities.add(identity)

    def remove_identity(self, identity: str) -> None:
        """Remove an allowed identity."""
        self._allowed_identities.discard(identity)

    def verify_identity(self, identity: str) -> bool:
        """Verify if identity is allowed."""
        if not self._allowed_identities:
            return True
        return identity in self._allowed_identities

    async def check_access(self, client_addr: str, target: Address) -> bool:
        """
        Check if client can access target.

        Args:
            client_addr: Client address string
            target: Target address

        Returns:
            True if access is allowed
        """
        client_ip = client_addr.rsplit(":", 1)[0]

        if self._ip_blacklist:
            try:
                ip = ipaddress.ip_address(client_ip)
                for network in self._ip_blacklist:
                    if ip in network:
                        logger.warning(f"Client {client_addr} in blacklist")
                        return False
            except ValueError:
                pass

        if self._ip_whitelist:
            try:
                ip = ipaddress.ip_address(client_ip)
                in_whitelist = any(ip in network for network in self._ip_whitelist)
                if not in_whitelist:
                    logger.warning(f"Client {client_addr} not in whitelist")
                    return False
            except ValueError:
                pass

        for rule in self._access_rules:
            if rule.matches(target):
                return rule.allowed

        return self._default_allow

    def add_access_rule(self, rule: AccessRule) -> None:
        """Add an access rule."""
        self._access_rules.append(rule)

    def remove_access_rule(self, name: str) -> None:
        """Remove an access rule by name."""
        self._access_rules = [r for r in self._access_rules if r.name != name]

    @classmethod
    def from_config(cls, config: dict) -> Self:
        """Create from configuration dictionary."""
        rules = []
        for rule_config in config.get("access_rules", []):
            rules.append(AccessRule(
                name=rule_config.get("name", ""),
                allowed=rule_config.get("allowed", True),
                networks=rule_config.get("networks", []),
                domains=rule_config.get("domains", []),
                ports=rule_config.get("ports", []),
            ))

        return cls(
            allowed_identities=config.get("allowed_identities"),
            ip_whitelist=config.get("ip_whitelist"),
            ip_blacklist=config.get("ip_blacklist"),
            access_rules=rules,
            default_allow=config.get("default_allow", True),
        )
