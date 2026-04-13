"""Tests for client rules matcher."""

import pytest

from linkman.client.rules.matcher import (
    Rule,
    RuleType,
    RuleAction,
    RuleMatcher,
    MatchResult,
)
from linkman.shared.protocol.types import Address, AddressType


class TestRule:
    """Test Rule class."""

    def test_domain_match(self):
        rule = Rule(
            type=RuleType.DOMAIN,
            pattern="google.com",
            action=RuleAction.PROXY,
        )
        
        assert rule.matches("google.com", 443)
        assert not rule.matches("www.google.com", 443)
        assert not rule.matches("example.com", 443)

    def test_domain_suffix_match(self):
        rule = Rule(
            type=RuleType.DOMAIN_SUFFIX,
            pattern="google.com",
            action=RuleAction.PROXY,
        )
        
        assert rule.matches("google.com", 443)
        assert rule.matches("www.google.com", 443)
        assert rule.matches("mail.google.com", 443)
        assert not rule.matches("google.com.evil.com", 443)
        assert not rule.matches("example.com", 443)

    def test_domain_keyword_match(self):
        rule = Rule(
            type=RuleType.DOMAIN_KEYWORD,
            pattern="google",
            action=RuleAction.PROXY,
        )
        
        assert rule.matches("google.com", 443)
        assert rule.matches("www.google.com", 443)
        assert rule.matches("googleapis.com", 443)
        assert not rule.matches("example.com", 443)

    def test_ip_cidr_match(self):
        rule = Rule(
            type=RuleType.IP_CIDR,
            pattern="192.168.0.0/16",
            action=RuleAction.DIRECT,
        )
        
        assert rule.matches("192.168.1.1", 443)
        assert rule.matches("192.168.100.100", 443)
        assert not rule.matches("10.0.0.1", 443)

    def test_port_match(self):
        rule = Rule(
            type=RuleType.PORT,
            pattern="443",
            action=RuleAction.PROXY,
        )
        
        assert rule.matches("example.com", 443)
        assert not rule.matches("example.com", 80)

    def test_port_range_match(self):
        rule = Rule(
            type=RuleType.PORT,
            pattern="8000-9000",
            action=RuleAction.DIRECT,
        )
        
        assert rule.matches("example.com", 8000)
        assert rule.matches("example.com", 8500)
        assert rule.matches("example.com", 9000)
        assert not rule.matches("example.com", 80)

    def test_final_match(self):
        rule = Rule(
            type=RuleType.FINAL,
            pattern="",
            action=RuleAction.DIRECT,
        )
        
        assert rule.matches("anything.com", 443)
        assert rule.matches("192.168.1.1", 80)


class TestRuleMatcher:
    """Test RuleMatcher class."""

    def test_default_rules_loaded(self):
        matcher = RuleMatcher()
        rules = matcher.get_rules()
        
        assert len(rules) > 0

    def test_add_rule(self):
        matcher = RuleMatcher()
        initial_count = len(matcher.get_rules())
        
        matcher.add_rule("test.com", is_proxy=True)
        
        assert len(matcher.get_rules()) == initial_count + 1

    def test_remove_rule(self):
        matcher = RuleMatcher()
        matcher.add_rule("test.com", is_proxy=True)
        
        result = matcher.remove_rule("test.com")
        
        assert result is True

    def test_match_proxy_domain(self):
        matcher = RuleMatcher()
        matcher.clear_rules()
        matcher.add_rule("google.com", is_proxy=True, rule_type="domain_suffix")
        matcher.add_rule("", is_proxy=False, rule_type="final")
        
        addr = Address.from_host_port("www.google.com", 443)
        result = matcher.match(addr)
        
        assert result.matched
        assert result.is_proxy

    def test_match_direct_ip(self):
        matcher = RuleMatcher()
        matcher.clear_rules()
        matcher.add_rule("192.168.0.0/16", is_proxy=False, rule_type="ip_cidr")
        matcher.add_rule("", is_proxy=True, rule_type="final")
        
        addr = Address.from_host_port("192.168.1.1", 443)
        result = matcher.match(addr)
        
        assert result.matched
        assert result.is_direct

    def test_priority_order(self):
        matcher = RuleMatcher()
        matcher.clear_rules()
        
        matcher.add_rule("example.com", is_proxy=True, rule_type="domain_suffix", priority=10)
        matcher.add_rule("example.com", is_proxy=False, rule_type="domain_suffix", priority=5)
        
        addr = Address.from_host_port("example.com", 443)
        result = matcher.match(addr)
        
        assert result.is_proxy

    def test_load_rules(self):
        matcher = RuleMatcher()
        
        rules = [
            {"type": "domain_suffix", "pattern": "google.com", "action": "proxy"},
            {"type": "domain_suffix", "pattern": "youtube.com", "action": "proxy"},
        ]
        
        matcher.load_rules(rules)
        
        assert len(matcher.get_rules()) == 2


class TestMatchResult:
    """Test MatchResult class."""

    def test_default_values(self):
        result = MatchResult()
        
        assert result.matched is False
        assert result.is_proxy is False
        assert result.is_direct is False
        assert result.is_block is False
        assert result.rule is None
