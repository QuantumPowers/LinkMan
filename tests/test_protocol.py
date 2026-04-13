"""Tests for protocol module."""

import pytest

from linkman.shared.protocol.types import (
    Address,
    AddressType,
    Command,
    ProtocolError,
    ReplyCode,
    Request,
    Response,
)


class TestAddress:
    """Test Address class."""

    def test_ipv4_address(self):
        addr = Address(host="192.168.1.1", port=8080, addr_type=AddressType.IPV4)
        
        assert addr.host == "192.168.1.1"
        assert addr.port == 8080
        assert addr.is_ipv4
        assert not addr.is_ipv6
        assert not addr.is_domain

    def test_ipv6_address(self):
        addr = Address(host="::1", port=443, addr_type=AddressType.IPV6)
        
        assert addr.host == "::1"
        assert addr.port == 443
        assert addr.is_ipv6

    def test_domain_address(self):
        addr = Address(host="example.com", port=443, addr_type=AddressType.DOMAIN)
        
        assert addr.host == "example.com"
        assert addr.is_domain

    def test_from_host_port_ipv4(self):
        addr = Address.from_host_port("10.0.0.1", 80)
        
        assert addr.addr_type == AddressType.IPV4
        assert addr.host == "10.0.0.1"

    def test_from_host_port_ipv6(self):
        addr = Address.from_host_port("2001:db8::1", 443)
        
        assert addr.addr_type == AddressType.IPV6

    def test_from_host_port_domain(self):
        addr = Address.from_host_port("google.com", 443)
        
        assert addr.addr_type == AddressType.DOMAIN
        assert addr.host == "google.com"

    def test_invalid_port(self):
        with pytest.raises(ValueError):
            Address(host="localhost", port=70000, addr_type=AddressType.DOMAIN)

        with pytest.raises(ValueError):
            Address(host="localhost", port=-1, addr_type=AddressType.DOMAIN)

    def test_to_bytes_ipv4(self):
        addr = Address(host="192.168.1.1", port=8080, addr_type=AddressType.IPV4)
        data = addr.to_bytes()
        
        assert data[0] == AddressType.IPV4
        assert len(data) == 7

    def test_to_bytes_domain(self):
        addr = Address(host="example.com", port=443, addr_type=AddressType.DOMAIN)
        data = addr.to_bytes()
        
        assert data[0] == AddressType.DOMAIN
        assert len(data) == 4 + len("example.com")

    def test_from_bytes_ipv4(self):
        original = Address(host="192.168.1.1", port=8080, addr_type=AddressType.IPV4)
        data = original.to_bytes()
        
        restored, consumed = Address.from_bytes(data)
        
        assert restored.host == original.host
        assert restored.port == original.port
        assert consumed == 7

    def test_from_bytes_domain(self):
        original = Address(host="example.com", port=443, addr_type=AddressType.DOMAIN)
        data = original.to_bytes()
        
        restored, consumed = Address.from_bytes(data)
        
        assert restored.host == original.host
        assert restored.port == original.port

    def test_str_representation(self):
        ipv4 = Address(host="192.168.1.1", port=8080, addr_type=AddressType.IPV4)
        assert str(ipv4) == "192.168.1.1:8080"
        
        ipv6 = Address(host="::1", port=443, addr_type=AddressType.IPV6)
        assert str(ipv6) == "[::1]:443"
        
        domain = Address(host="example.com", port=443, addr_type=AddressType.DOMAIN)
        assert str(domain) == "example.com:443"


class TestRequest:
    """Test Request class."""

    def test_connect_request(self):
        addr = Address.from_host_port("example.com", 443)
        request = Request(command=Command.CONNECT, address=addr)
        
        assert request.command == Command.CONNECT
        assert request.address.host == "example.com"

    def test_to_bytes(self):
        addr = Address.from_host_port("example.com", 443)
        request = Request(command=Command.CONNECT, address=addr)
        
        data = request.to_bytes()
        
        assert data[0] == Command.CONNECT

    def test_from_bytes(self):
        addr = Address.from_host_port("example.com", 443)
        original = Request(command=Command.CONNECT, address=addr)
        data = original.to_bytes()
        
        restored = Request.from_bytes(data)
        
        assert restored.command == original.command
        assert restored.address.host == original.address.host
        assert restored.address.port == original.address.port


class TestResponse:
    """Test Response class."""

    def test_success_response(self):
        response = Response.success()
        
        assert response.reply_code == ReplyCode.SUCCEEDED

    def test_failure_response(self):
        response = Response.failure(ReplyCode.CONNECTION_REFUSED)
        
        assert response.reply_code == ReplyCode.CONNECTION_REFUSED

    def test_to_bytes(self):
        response = Response.success()
        data = response.to_bytes()
        
        assert data[0] == ReplyCode.SUCCEEDED


class TestProtocolError:
    """Test ProtocolError."""

    def test_error_with_reply_code(self):
        error = ProtocolError("Connection failed", ReplyCode.CONNECTION_REFUSED)
        
        assert str(error) == "Connection failed"
        assert error.reply_code == ReplyCode.CONNECTION_REFUSED

    def test_error_without_reply_code(self):
        error = ProtocolError("Generic error")
        
        assert error.reply_code is None
