"""
UDP handler for LinkMan VPN server.

Handles UDP associate requests and UDP packet relay.
"""

from __future__ import annotations

import asyncio
import socket
from typing import Dict, Optional, Tuple

from linkman.shared.crypto.aead import AEADCipher, AEADType
from linkman.shared.protocol.types import Address, ReplyCode, Response
from linkman.shared.utils.logger import get_logger

logger = get_logger("server.udp")


class UDPServer:
    """
    UDP server for handling UDP associate requests.
    
    Manages:
    - UDP socket for receiving and sending packets
    - Client UDP associations
    - Packet encryption and decryption
    - Relay to target hosts
    """

    def __init__(self, key: bytes, cipher_type: AEADType):
        """
        Initialize UDP server.

        Args:
            key: Encryption key
            cipher_type: AEAD cipher type
        """
        self._key = key
        self._cipher_type = cipher_type
        self._socket: Optional[socket.socket] = None
        self._server: Optional[asyncio.AbstractServer] = None
        self._associations: Dict[str, Tuple[Address, AEADCipher]] = {}
        self._running = False

    async def start(self, host: str = "0.0.0.0", port: int = 0) -> Tuple[str, int]:
        """
        Start the UDP server.

        Args:
            host: Host to bind to
            port: Port to bind to (0 for random)

        Returns:
            Tuple of (host, port) the server is listening on
        """
        if self._running:
            raise RuntimeError("UDP server already running")

        # Create UDP socket
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((host, port))
        self._socket.setblocking(False)

        # Start asyncio datagram endpoint for UDP
        class UDPProtocol(asyncio.DatagramProtocol):
            def __init__(self, handler):
                self.handler = handler

            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, data, addr):
                # Handle UDP datagram
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
        """
        Stop the UDP server.
        """
        if not self._running:
            return

        self._running = False

        if self._transport:
            self._transport.close()

        if self._socket:
            self._socket.close()

        self._associations.clear()
        logger.info("UDP server stopped")

    async def _process_udp_packet(self, data: bytes, client_addr: str) -> None:
        """
        Process incoming UDP packet.

        Args:
            data: Encrypted UDP packet
            client_addr: Client address
        """
        if not data or not self._running:
            return

        # Parse and decrypt packet
        try:
            # Extract salt (first 16 bytes)
            if len(data) < 16:
                logger.warning(f"Invalid UDP packet from {client_addr}: too short")
                return

            salt = data[:16]
            encrypted_data = data[16:]

            # Create cipher with salt
            cipher = AEADCipher(self._cipher_type, self._key, salt)

            # Decrypt packet
            payload, _ = cipher.decrypt_packet(encrypted_data)

            # Parse UDP request
            if len(payload) < 3:
                logger.warning(f"Invalid UDP payload from {client_addr}: too short")
                return

            # First byte is reserved (0x00)
            # Second byte is frag (fragment number, 0 for no fragmentation)
            frag = payload[1]
            if frag != 0:
                logger.warning(f"UDP fragmentation not supported from {client_addr}")
                return

            # Parse address
            addr, addr_len = Address.from_bytes(payload, offset=2)
            udp_data = payload[2 + addr_len:]

            if not udp_data:
                return

            # Relay UDP data to target
            await self._relay_udp(addr, udp_data, client_addr, cipher)

        except Exception as e:
            logger.error(f"Error processing UDP packet from {client_addr}: {e}")

    async def _relay_udp(self, addr: Address, data: bytes, client_addr: str, 
                         cipher: AEADCipher) -> None:
        """
        Relay UDP data to target and send response back.

        Args:
            addr: Target address
            data: UDP data to send
            client_addr: Client address
            cipher: Cipher for encryption
        """
        try:
            # Create UDP socket for relay
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.setblocking(False)

            # Send data to target
            await asyncio.get_event_loop().sock_sendto(
                udp_socket,
                data,
                (addr.host, addr.port)
            )

            # Receive response (with timeout)
            try:
                response, _ = await asyncio.wait_for(
                    asyncio.get_event_loop().sock_recvfrom(udp_socket, 65536),
                    timeout=5.0
                )

                # Send response back to client
                await self._send_udp_response(addr, response, client_addr, cipher)
            except asyncio.TimeoutError:
                # No response, nothing to send back
                pass
            finally:
                udp_socket.close()

        except Exception as e:
            logger.error(f"Error relaying UDP data to {addr}: {e}")

    async def _send_udp_response(self, addr: Address, data: bytes, client_addr: str, 
                                cipher: AEADCipher) -> None:
        """
        Send UDP response back to client.

        Args:
            addr: Target address (for response)
            data: UDP response data
            client_addr: Client address
            cipher: Cipher for encryption
        """
        try:
            # Build response payload
            # Format: [0x00][frag=0][address][data]
            payload = b"\x00\x00" + addr.to_bytes() + data

            # Encrypt payload
            encrypted = cipher.encrypt_packet(payload)

            # Send response using transport
            if hasattr(self, '_transport') and self._transport:
                # Extract client IP and port from client_addr
                client_ip, client_port = client_addr.split(':')
                self._transport.sendto(
                    encrypted,
                    (client_ip, int(client_port))
                )

        except Exception as e:
            logger.error(f"Error sending UDP response to {client_addr}: {e}")

    def add_association(self, client_addr: str, addr: Address, cipher: AEADCipher) -> None:
        """
        Add a UDP association.

        Args:
            client_addr: Client address
            addr: Associated address
            cipher: Cipher for encryption/decryption
        """
        self._associations[client_addr] = (addr, cipher)

    def remove_association(self, client_addr: str) -> None:
        """
        Remove a UDP association.

        Args:
            client_addr: Client address
        """
        self._associations.pop(client_addr, None)
