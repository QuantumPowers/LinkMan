"""
UDP handler for LinkMan VPN server.

Handles UDP associate requests and UDP packet relay.
"""

from __future__ import annotations

import asyncio
import socket
from contextlib import asynccontextmanager
from typing import Dict, Optional, Tuple

from linkman.shared.crypto.aead import AEADCipher, AEADType
from linkman.shared.protocol.types import Address, ReplyCode, Response
from linkman.shared.utils.logger import get_logger

logger = get_logger("server.udp")

_UDP_POOL_SIZE = 32
_UDP_RELAY_TIMEOUT = 5.0
_UDP_BUF_SIZE = 65536


class _UDPRelayPool:
    """Reusable UDP socket pool for relay operations."""

    def __init__(self, pool_size: int = _UDP_POOL_SIZE):
        self._pool: list[socket.socket] = []
        self._pool_size = pool_size
        self._lock = asyncio.Lock()

    async def acquire(self) -> socket.socket:
        async with self._lock:
            if self._pool:
                return self._pool.pop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        return sock

    async def release(self, sock: socket.socket) -> None:
        async with self._lock:
            if len(self._pool) < self._pool_size:
                self._pool.append(sock)
            else:
                sock.close()

    async def close_all(self) -> None:
        async with self._lock:
            for sock in self._pool:
                try:
                    sock.close()
                except Exception:
                    pass
            self._pool.clear()


_relay_pool = _UDPRelayPool()


class UDPServer:
    """
    UDP server for handling UDP associate requests.

    Manages:
    - UDP socket for receiving and sending packets
    - Client UDP associations
    - Packet encryption and decryption
    - Relay to target hosts via shared socket pool
    """

    def __init__(self, key: bytes, cipher_type: AEADType):
        self._key = key
        self._cipher_type = cipher_type
        self._socket: Optional[socket.socket] = None
        self._server: Optional[asyncio.AbstractServer] = None
        self._associations: Dict[str, Tuple[Address, AEADCipher]] = {}
        self._running = False
        self._transport = None
        self._protocol = None

    async def start(self, host: str = "0.0.0.0", port: int = 0) -> Tuple[str, int]:
        if self._running:
            raise RuntimeError("UDP server already running")

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((host, port))
        self._socket.setblocking(False)

        class UDPProtocol(asyncio.DatagramProtocol):
            def __init__(self, handler):
                self.handler = handler

            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, data, addr):
                client_addr = f"{addr[0]}:{addr[1]}"
                asyncio.create_task(self.handler._process_udp_packet(data, client_addr))

            def error_received(self, exc):
                logger.error(f"UDP error: {exc}")

            def connection_lost(self, exc):
                if exc:
                    logger.error(f"UDP connection lost: {exc}")

        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: UDPProtocol(self),
            sock=self._socket
        )

        self._transport = transport
        self._protocol = protocol
        self._running = True
        addr = self._socket.getsockname()
        logger.info(f"UDP server started on {addr[0]}:{addr[1]}")
        return addr[0], addr[1]

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False

        if self._transport:
            self._transport.close()

        if self._socket:
            self._socket.close()

        self._associations.clear()
        await _relay_pool.close_all()
        logger.info("UDP server stopped")

    async def _process_udp_packet(self, data: bytes, client_addr: str) -> None:
        if not data or not self._running:
            return

        try:
            if len(data) < 16:
                logger.warning(f"Invalid UDP packet from {client_addr}: too short")
                return

            salt = data[:16]
            encrypted_data = data[16:]

            cipher = AEADCipher(self._cipher_type, self._key, salt)

            payload, _ = cipher.decrypt_packet(encrypted_data)

            if len(payload) < 3:
                logger.warning(f"Invalid UDP payload from {client_addr}: too short")
                return

            frag = payload[1]
            if frag != 0:
                logger.warning(f"UDP fragmentation not supported from {client_addr}")
                return

            addr, addr_len = Address.from_bytes(payload, offset=2)
            udp_data = payload[2 + addr_len:]

            if not udp_data:
                return

            await self._relay_udp(addr, udp_data, client_addr, cipher)

        except Exception as e:
            logger.error(f"Error processing UDP packet from {client_addr}: {e}")

    async def _relay_udp(self, addr: Address, data: bytes, client_addr: str,
                         cipher: AEADCipher) -> None:
        udp_socket = await _relay_pool.acquire()
        try:
            loop = asyncio.get_event_loop()
            await loop.sock_sendto(udp_socket, data, (addr.host, addr.port))

            try:
                response, _ = await asyncio.wait_for(
                    loop.sock_recvfrom(udp_socket, _UDP_BUF_SIZE),
                    timeout=_UDP_RELAY_TIMEOUT,
                )
                await self._send_udp_response(addr, response, client_addr, cipher)
            except asyncio.TimeoutError:
                pass
        except Exception as e:
            logger.error(f"Error relaying UDP data to {addr}: {e}")
        finally:
            await _relay_pool.release(udp_socket)

    async def _send_udp_response(self, addr: Address, data: bytes, client_addr: str,
                                cipher: AEADCipher) -> None:
        try:
            payload = b"\x00\x00" + addr.to_bytes() + data
            encrypted = cipher.encrypt_packet(payload)

            if self._transport:
                client_ip, client_port = client_addr.split(':')
                self._transport.sendto(
                    encrypted,
                    (client_ip, int(client_port))
                )

        except Exception as e:
            logger.error(f"Error sending UDP response to {client_addr}: {e}")

    def add_association(self, client_addr: str, addr: Address, cipher: AEADCipher) -> None:
        self._associations[client_addr] = (addr, cipher)

    def remove_association(self, client_addr: str) -> None:
        self._associations.pop(client_addr, None)
