"""
Protocol types and definitions for Shadowsocks 2022.

Implements the SOCKS5-like protocol used by Shadowsocks 2022
with address parsing, request/response handling.
"""

from __future__ import annotations

import ipaddress
import socket
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import ClassVar


class Command(IntEnum):
    """SOCKS5 command types."""

    CONNECT = 0x01
    UDP_ASSOCIATE = 0x03


class AddressType(IntEnum):
    """Address type codes."""

    IPV4 = 0x01
    DOMAIN = 0x03
    IPV6 = 0x04


class ReplyCode(IntEnum):
    """SOCKS5 reply codes."""

    SUCCEEDED = 0x00
    GENERAL_FAILURE = 0x01
    CONNECTION_NOT_ALLOWED = 0x02
    NETWORK_UNREACHABLE = 0x03
    HOST_UNREACHABLE = 0x04
    CONNECTION_REFUSED = 0x05
    TTL_EXPIRED = 0x06
    COMMAND_NOT_SUPPORTED = 0x07
    ADDRESS_TYPE_NOT_SUPPORTED = 0x08


class ProtocolError(Exception):
    """Protocol-related errors."""

    def __init__(self, message: str, reply_code: ReplyCode | None = None):
        super().__init__(message)
        self.reply_code = reply_code


@dataclass(frozen=True)
class Address:
    """
    Network address representation.

    Supports IPv4, IPv6, and domain names.
    """

    host: str
    port: int
    addr_type: AddressType

    MAX_DOMAIN_LENGTH: ClassVar[int] = 255
    MAX_PORT: ClassVar[int] = 65535

    def __post_init__(self) -> None:
        """Validate address."""
        if self.port < 0 or self.port > self.MAX_PORT:
            raise ValueError(f"Invalid port: {self.port}")

        if self.addr_type == AddressType.DOMAIN:
            if len(self.host) > self.MAX_DOMAIN_LENGTH:
                raise ValueError(f"Domain too long: {len(self.host)}")
        elif self.addr_type == AddressType.IPV4:
            try:
                ipaddress.IPv4Address(self.host)
            except ipaddress.AddressValueError as e:
                raise ValueError(f"Invalid IPv4 address: {self.host}") from e
        elif self.addr_type == AddressType.IPV6:
            try:
                ipaddress.IPv6Address(self.host)
            except ipaddress.AddressValueError as e:
                raise ValueError(f"Invalid IPv6 address: {self.host}") from e

    @classmethod
    def from_host_port(cls, host: str, port: int) -> "Address":
        """
        Create address from host and port.

        Automatically detects address type.

        Args:
            host: Hostname or IP address
            port: Port number

        Returns:
            Address instance
        """
        try:
            ipaddress.IPv4Address(host)
            return cls(host=host, port=port, addr_type=AddressType.IPV4)
        except ipaddress.AddressValueError:
            pass

        try:
            ipaddress.IPv6Address(host)
            return cls(host=host, port=port, addr_type=AddressType.IPV6)
        except ipaddress.AddressValueError:
            pass

        return cls(host=host, port=port, addr_type=AddressType.DOMAIN)

    def to_bytes(self) -> bytes:
        """
        Serialize address to bytes.

        Format:
        - IPv4: [0x01][4 bytes IP][2 bytes port]
        - Domain: [0x03][1 byte length][domain][2 bytes port]
        - IPv6: [0x04][16 bytes IP][2 bytes port]

        Returns:
            Serialized address
        """
        if self.addr_type == AddressType.IPV4:
            ip_bytes = socket.inet_pton(socket.AF_INET, self.host)
            return struct.pack("!B4sH", AddressType.IPV4, ip_bytes, self.port)
        elif self.addr_type == AddressType.DOMAIN:
            domain_bytes = self.host.encode("idna")
            return struct.pack("!BB", AddressType.DOMAIN, len(domain_bytes)) + domain_bytes + struct.pack("!H", self.port)
        else:
            ip_bytes = socket.inet_pton(socket.AF_INET6, self.host)
            return struct.pack("!B16sH", AddressType.IPV6, ip_bytes, self.port)

    @classmethod
    def from_bytes(cls, data: bytes, offset: int = 0) -> tuple["Address", int]:
        """
        Parse address from bytes.

        Args:
            data: Byte data
            offset: Starting offset

        Returns:
            Tuple of (Address, bytes consumed)

        Raises:
            ProtocolError: If parsing fails
        """
        if len(data) < offset + 1:
            raise ProtocolError("Insufficient data for address type")

        addr_type = AddressType(data[offset])

        if addr_type == AddressType.IPV4:
            if len(data) < offset + 7:
                raise ProtocolError("Insufficient data for IPv4 address")
            ip_bytes = data[offset + 1 : offset + 5]
            host = socket.inet_ntop(socket.AF_INET, ip_bytes)
            port = struct.unpack("!H", data[offset + 5 : offset + 7])[0]
            return cls(host=host, port=port, addr_type=addr_type), 7

        elif addr_type == AddressType.DOMAIN:
            if len(data) < offset + 2:
                raise ProtocolError("Insufficient data for domain length")
            domain_len = data[offset + 1]
            if len(data) < offset + 4 + domain_len:
                raise ProtocolError("Insufficient data for domain")
            host = data[offset + 2 : offset + 2 + domain_len].decode("idna")
            port = struct.unpack("!H", data[offset + 2 + domain_len : offset + 4 + domain_len])[0]
            return cls(host=host, port=port, addr_type=addr_type), 4 + domain_len

        elif addr_type == AddressType.IPV6:
            if len(data) < offset + 19:
                raise ProtocolError("Insufficient data for IPv6 address")
            ip_bytes = data[offset + 1 : offset + 17]
            host = socket.inet_ntop(socket.AF_INET6, ip_bytes)
            port = struct.unpack("!H", data[offset + 17 : offset + 19])[0]
            return cls(host=host, port=port, addr_type=addr_type), 19

        else:
            raise ProtocolError(f"Unknown address type: {addr_type}", ReplyCode.ADDRESS_TYPE_NOT_SUPPORTED)

    @property
    def is_ipv4(self) -> bool:
        """Check if address is IPv4."""
        return self.addr_type == AddressType.IPV4

    @property
    def is_ipv6(self) -> bool:
        """Check if address is IPv6."""
        return self.addr_type == AddressType.IPV6

    @property
    def is_domain(self) -> bool:
        """Check if address is a domain name."""
        return self.addr_type == AddressType.DOMAIN

    def __str__(self) -> str:
        """Return string representation."""
        if self.addr_type == AddressType.IPV6:
            return f"[{self.host}]:{self.port}"
        return f"{self.host}:{self.port}"


@dataclass
class Request:
    """Proxy request."""

    command: Command
    address: Address

    def to_bytes(self) -> bytes:
        """
        Serialize request to bytes.

        Format: [command][address]

        Returns:
            Serialized request
        """
        return bytes([self.command]) + self.address.to_bytes()

    @classmethod
    def from_bytes(cls, data: bytes) -> "Request":
        """
        Parse request from bytes.

        Args:
            data: Byte data

        Returns:
            Request instance

        Raises:
            ProtocolError: If parsing fails
        """
        if len(data) < 1:
            raise ProtocolError("Empty request data")

        try:
            command = Command(data[0])
        except ValueError as e:
            raise ProtocolError(f"Unknown command: {data[0]}", ReplyCode.COMMAND_NOT_SUPPORTED) from e

        address, _ = Address.from_bytes(data, offset=1)
        return cls(command=command, address=address)


@dataclass
class Response:
    """Proxy response."""

    reply_code: ReplyCode
    bind_address: Address | None = None

    def to_bytes(self) -> bytes:
        """
        Serialize response to bytes.

        Format: [reply_code][bind_address]

        Returns:
            Serialized response
        """
        data = bytes([self.reply_code])
        if self.bind_address:
            data += self.bind_address.to_bytes()
        else:
            data += Address(host="0.0.0.0", port=0, addr_type=AddressType.IPV4).to_bytes()
        return data

    @classmethod
    def success(cls, bind_address: Address | None = None) -> "Response":
        """Create a success response."""
        return cls(reply_code=ReplyCode.SUCCEEDED, bind_address=bind_address)

    @classmethod
    def failure(cls, reply_code: ReplyCode) -> "Response":
        """Create a failure response."""
        return cls(reply_code=reply_code)
