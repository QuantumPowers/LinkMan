"""
WebSocket handler for LinkMan VPN server.

Handles WebSocket connections for traffic obfuscation.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import aiohttp
from aiohttp import web

from linkman.shared.crypto.aead import AEADCipher, AEADType
from linkman.shared.protocol.types import Address, Command, ProtocolError, ReplyCode, Request, Response
from linkman.shared.utils.logger import get_logger

logger = get_logger("server.websocket")


class WebSocketHandler:
    """
    WebSocket handler for LinkMan VPN.
    
    Handles WebSocket connections and relays data to/from the VPN protocol.
    """

    def __init__(
        self,
        key: bytes,
        cipher_type: AEADType,
        connection_handler: "ConnectionHandler",
    ):
        """
        Initialize WebSocket handler.

        Args:
            key: Encryption key
            cipher_type: AEAD cipher type
            connection_handler: Connection handler instance
        """
        self._key = key
        self._cipher_type = cipher_type
        self._connection_handler = connection_handler

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """
        Handle WebSocket connection.

        Args:
            request: HTTP request

        Returns:
            WebSocket response
        """
        # Add common HTTP headers to disguise as regular web traffic
        ws = web.WebSocketResponse(
            headers={
                'Server': 'nginx',
                'X-Powered-By': 'PHP/7.4.33',
                'Content-Type': 'application/json'
            }
        )
        await ws.prepare(request)

        peername = request.transport.get_extra_info('peername')
        client_addr = f"{peername[0]}:{peername[1]}" if peername else "unknown"

        logger.info(f"New WebSocket connection from {client_addr}")

        cipher: Optional[AEADCipher] = None
        target_reader: Optional[asyncio.StreamReader] = None
        target_writer: Optional[asyncio.StreamWriter] = None

        try:
            # Handle WebSocket messages
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    if not cipher:
                        # First message should be the salt
                        if len(msg.data) < 16:
                            logger.warning(f"Invalid WebSocket message from {client_addr}: too short")
                            await ws.close(code=1008, message=b"Invalid message")
                            return ws

                        salt = msg.data[:16]
                        cipher = AEADCipher(self._cipher_type, self._key, salt)
                        logger.debug(f"WebSocket handshake completed with {client_addr}")
                    else:
                        # Process encrypted data
                        try:
                            payload, _ = cipher.decrypt_packet(msg.data)
                            if not payload:
                                continue

                            # Handle request
                            request = Request.from_bytes(payload)
                            if request.command == Command.CONNECT:
                                await self._handle_connect(ws, cipher, request.address, client_addr)
                            elif request.command == Command.UDP_ASSOCIATE:
                                await self._handle_udp_associate(ws, cipher, request.address, client_addr)
                            else:
                                logger.warning(f"Unknown command: {request.command}")
                                response = Response.error(ReplyCode.COMMAND_NOT_SUPPORTED)
                                encrypted_response = cipher.encrypt_packet(response.to_bytes())
                                await ws.send_bytes(encrypted_response)

                        except Exception as e:
                            logger.error(f"Error processing WebSocket message: {e}")
                            response = Response.error(ReplyCode.GENERAL_FAILURE)
                            encrypted_response = cipher.encrypt_packet(response.to_bytes())
                            await ws.send_bytes(encrypted_response)

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error from {client_addr}: {ws.exception()}")
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info(f"WebSocket connection closed from {client_addr}")
                    break

        except Exception as e:
            logger.error(f"Error handling WebSocket connection: {e}")
        finally:
            # Clean up
            if target_writer:
                target_writer.close()
                await target_writer.wait_closed()
            if ws and not ws.closed:
                await ws.close()

        return ws

    async def _handle_connect(self, ws: web.WebSocketResponse, cipher: AEADCipher, 
                             address: Address, client_addr: str) -> None:
        """
        Handle CONNECT command over WebSocket.

        Args:
            ws: WebSocket response
            cipher: AEAD cipher
            address: Target address
            client_addr: Client address
        """
        try:
            # Check access
            if not await self._connection_handler.check_access(client_addr, address):
                response = Response.error(ReplyCode.CONNECTION_NOT_ALLOWED)
                encrypted_response = cipher.encrypt_packet(response.to_bytes())
                await ws.send_bytes(encrypted_response)
                return

            # Connect to target
            target_reader, target_writer = await asyncio.wait_for(
                asyncio.open_connection(address.host, address.port),
                timeout=15,
            )

            # Send success response
            response = Response.success()
            encrypted_response = cipher.encrypt_packet(response.to_bytes())
            await ws.send_bytes(encrypted_response)

            logger.info(f"WebSocket connected: {client_addr} -> {address}")

            # Start relay tasks
            async def relay_to_target():
                try:
                    while not ws.closed:
                        msg = await ws.receive()
                        if msg.type == aiohttp.WSMsgType.BINARY:
                            payload, _ = cipher.decrypt_packet(msg.data)
                            if payload:
                                target_writer.write(payload)
                                await target_writer.drain()
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
                except Exception as e:
                    logger.debug(f"Error relaying to target: {e}")

            async def relay_to_client():
                try:
                    while not ws.closed:
                        data = await target_reader.read(65536)
                        if not data:
                            break
                        encrypted = cipher.encrypt_packet(data)
                        await ws.send_bytes(encrypted)
                except Exception as e:
                    logger.debug(f"Error relaying to client: {e}")

            # Run relay tasks
            await asyncio.gather(relay_to_target(), relay_to_client())

        except asyncio.TimeoutError:
            response = Response.error(ReplyCode.TTL_EXPIRED)
            encrypted_response = cipher.encrypt_packet(response.to_bytes())
            await ws.send_bytes(encrypted_response)
        except Exception as e:
            logger.error(f"Error handling WebSocket connect: {e}")
            response = Response.error(ReplyCode.GENERAL_FAILURE)
            encrypted_response = cipher.encrypt_packet(response.to_bytes())
            await ws.send_bytes(encrypted_response)

    async def _handle_udp_associate(self, ws: web.WebSocketResponse, cipher: AEADCipher, 
                                   address: Address, client_addr: str) -> None:
        """
        Handle UDP ASSOCIATE command over WebSocket.

        Args:
            ws: WebSocket response
            cipher: AEAD cipher
            address: Target address
            client_addr: Client address
        """
        try:
            # Check access
            if not await self._connection_handler.check_access(client_addr, address):
                response = Response.error(ReplyCode.CONNECTION_NOT_ALLOWED)
                encrypted_response = cipher.encrypt_packet(response.to_bytes())
                await ws.send_bytes(encrypted_response)
                return

            # Get UDP server port
            udp_port = self._connection_handler.udp_server_port
            if udp_port == 0:
                response = Response.error(ReplyCode.GENERAL_FAILURE)
                encrypted_response = cipher.encrypt_packet(response.to_bytes())
                await ws.send_bytes(encrypted_response)
                return

            # Create bind address
            bind_address = Address(host="0.0.0.0", port=udp_port, addr_type=address.addr_type)

            # Send success response
            response = Response.success(bind_address)
            encrypted_response = cipher.encrypt_packet(response.to_bytes())
            await ws.send_bytes(encrypted_response)

            logger.info(f"WebSocket UDP associate established: {client_addr} -> UDP port {udp_port}")

            # Keep connection alive for UDP association
            await asyncio.sleep(300)  # 5 minutes timeout

        except Exception as e:
            logger.error(f"Error handling WebSocket UDP associate: {e}")
            response = Response.error(ReplyCode.GENERAL_FAILURE)
            encrypted_response = cipher.encrypt_packet(response.to_bytes())
            await ws.send_bytes(encrypted_response)
