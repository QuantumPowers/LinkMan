"""
Connection pool management for LinkMan VPN.

Provides connection pooling and health checking for better performance and reliability.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable

from linkman.shared.utils.logger import get_logger

logger = get_logger("utils.connection_pool")


@dataclass
class Connection:
    """Connection object."""
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    is_healthy: bool = True
    usage_count: int = 0


class ConnectionPool:
    """
    Connection pool for managing and reusing connections.
    
    Features:
    - Connection pooling and reuse
    - Advanced connection health checking
    - Automatic connection cleanup
    - Connection timeout management
    - Connection age and idle time checks
    - Thread-safe operations
    """
    
    def __init__(
        self,
        create_connection: Callable[[], asyncio.coroutine],
        max_connections: int = 100,
        max_idle_time: float = 300.0,  # 5 minutes
        health_check_interval: float = 60.0,  # 1 minute
        max_usage_per_connection: int = 1000,
    ):
        """
        Initialize connection pool.
        
        Args:
            create_connection: Function to create a new connection
            max_connections: Maximum number of connections
            max_idle_time: Maximum idle time for connections
            health_check_interval: Interval for health checks
            max_usage_per_connection: Maximum usage count per connection
        """
        self._create_connection = create_connection
        self._max_connections = max_connections
        self._max_idle_time = max_idle_time
        self._health_check_interval = health_check_interval
        self._max_usage_per_connection = max_usage_per_connection
        
        self._connections: List[Connection] = []
        self._in_use: Dict[int, Connection] = {}
        self._lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        """Start the connection pool."""
        if not self._running:
            self._running = True
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info(f"Connection pool started with max_connections={self._max_connections}")
    
    async def stop(self):
        """Stop the connection pool."""
        if self._running:
            self._running = False
            
            if self._health_check_task:
                self._health_check_task.cancel()
            if self._cleanup_task:
                self._cleanup_task.cancel()
            
            # Close all connections
            async with self._lock:
                for conn in self._connections:
                    try:
                        conn.writer.close()
                        await conn.writer.wait_closed()
                    except Exception as e:
                        logger.debug(f"Error closing connection: {e}")
                
                for conn in self._in_use.values():
                    try:
                        conn.writer.close()
                        await conn.writer.wait_closed()
                    except Exception as e:
                        logger.debug(f"Error closing in-use connection: {e}")
                
                self._connections.clear()
                self._in_use.clear()
            
            logger.info("Connection pool stopped")
    
    async def get_connection(self, timeout: float = 30.0) -> Connection:
        """
        Get a connection from the pool.
        
        Args:
            timeout: Maximum time to wait for a connection (seconds)
            
        Returns:
            Connection object
            
        Raises:
            TimeoutError: If no connection becomes available within the timeout period
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            async with self._lock:
                # Try to find an available connection
                for i, conn in enumerate(self._connections):
                    if conn.is_healthy and conn not in self._in_use.values():
                        # Mark connection as in use
                        conn_id = id(conn)
                        self._in_use[conn_id] = conn
                        conn.last_used = time.time()
                        conn.usage_count += 1
                        logger.debug(f"Reusing connection {conn_id}, usage count: {conn.usage_count}")
                        return conn
                
                # Create a new connection if pool is not full
                if len(self._connections) < self._max_connections:
                    try:
                        reader, writer = await self._create_connection()
                        conn = Connection(reader=reader, writer=writer)
                        conn_id = id(conn)
                        self._connections.append(conn)
                        self._in_use[conn_id] = conn
                        conn.usage_count += 1
                        logger.debug(f"Created new connection {conn_id}")
                        return conn
                    except Exception as e:
                        logger.error(f"Failed to create connection: {e}")
                        raise
                else:
                    # Wait for a connection to become available
                    logger.debug("Connection pool full, waiting for available connection")
                    
            # Wait for a short time before checking again
            await asyncio.sleep(0.1)
        
        # Timeout reached
        raise TimeoutError(f"No connection available within {timeout} seconds")
    
    async def return_connection(self, conn: Connection):
        """
        Return a connection to the pool.
        
        Args:
            conn: Connection to return
        """
        async with self._lock:
            conn_id = id(conn)
            if conn_id in self._in_use:
                del self._in_use[conn_id]
                conn.last_used = time.time()
                
                # Check if connection should be discarded
                if conn.usage_count >= self._max_usage_per_connection:
                    logger.debug(f"Connection {conn_id} reached max usage, discarding")
                    try:
                        conn.writer.close()
                        await conn.writer.wait_closed()
                    except Exception as e:
                        logger.debug(f"Error closing connection: {e}")
                    self._connections.remove(conn)
                elif not conn.is_healthy:
                    logger.debug(f"Connection {conn_id} is unhealthy, discarding")
                    try:
                        conn.writer.close()
                        await conn.writer.wait_closed()
                    except Exception as e:
                        logger.debug(f"Error closing connection: {e}")
                    self._connections.remove(conn)
            else:
                logger.warning(f"Returning connection {id(conn)} that was not in use")
    
    async def _health_check_loop(self):
        """Health check loop."""
        while self._running:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self._check_connections_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
    
    async def _cleanup_loop(self):
        """Cleanup loop for idle connections."""
        while self._running:
            try:
                await asyncio.sleep(60.0)  # Run every minute
                await self._cleanup_idle_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    async def _check_connections_health(self):
        """Check health of all connections."""
        async with self._lock:
            for conn in self._connections:
                if conn not in self._in_use.values():
                    if not await self._is_connection_healthy(conn):
                        conn.is_healthy = False
                        logger.debug(f"Connection {id(conn)} is unhealthy")
    
    async def _is_connection_healthy(self, conn: Connection) -> bool:
        """
        Check if a connection is healthy.
        
        Args:
            conn: Connection to check
            
        Returns:
            True if connection is healthy
        """
        try:
            # Check if connection is closing
            if conn.writer.transport.is_closing():
                return False
            
            # Check if connection is too old
            if time.time() - conn.created_at > 3600:  # 1 hour
                logger.debug(f"Connection {id(conn)} is too old")
                return False
            
            # Check if connection has been idle for too long
            if time.time() - conn.last_used > self._max_idle_time * 0.8:  # 80% of max idle time
                logger.debug(f"Connection {id(conn)} is nearly idle timeout")
                return False
            
            # Try to check if the connection is still readable
            try:
                # Set a short timeout for the read operation
                conn.writer.transport.set_read_timeout(0.1)
                # Check if there's any data available (non-blocking)
                if conn.reader.at_eof():
                    return False
            except Exception:
                # Ignore exceptions during read check
                pass
            finally:
                # Reset timeout
                try:
                    conn.writer.transport.set_read_timeout(None)
                except Exception:
                    pass
            
            return True
        except Exception as e:
            logger.debug(f"Connection health check failed: {e}")
            return False
    
    async def _cleanup_idle_connections(self):
        """Clean up idle connections."""
        now = time.time()
        async with self._lock:
            idle_connections = []
            for conn in self._connections:
                if conn not in self._in_use.values() and now - conn.last_used > self._max_idle_time:
                    idle_connections.append(conn)
            
            for conn in idle_connections:
                logger.debug(f"Cleaning up idle connection {id(conn)}")
                try:
                    conn.writer.close()
                    await conn.writer.wait_closed()
                except Exception as e:
                    logger.debug(f"Error closing idle connection: {e}")
                self._connections.remove(conn)
    
    @property
    def active_connections(self) -> int:
        """Get number of active connections."""
        return len(self._in_use)
    
    @property
    def total_connections(self) -> int:
        """Get total number of connections."""
        return len(self._connections)
    
    @property
    def available_connections(self) -> int:
        """Get number of available connections."""
        return len([c for c in self._connections if c.is_healthy and c not in self._in_use.values()])


class ConnectionPoolManager:
    """
    Manager for multiple connection pools.
    
    Allows managing connection pools for different servers or protocols.
    """
    
    def __init__(self):
        """Initialize connection pool manager."""
        self._pools: Dict[str, ConnectionPool] = {}
    
    def create_pool(
        self,
        name: str,
        create_connection: Callable[[], asyncio.coroutine],
        max_connections: int = 100,
        max_idle_time: float = 300.0,
        health_check_interval: float = 60.0,
        max_usage_per_connection: int = 1000,
    ) -> ConnectionPool:
        """
        Create a new connection pool.
        
        Args:
            name: Pool name
            create_connection: Function to create a new connection
            max_connections: Maximum number of connections
            max_idle_time: Maximum idle time for connections
            health_check_interval: Interval for health checks
            max_usage_per_connection: Maximum usage count per connection
            
        Returns:
            ConnectionPool instance
        """
        pool = ConnectionPool(
            create_connection=create_connection,
            max_connections=max_connections,
            max_idle_time=max_idle_time,
            health_check_interval=health_check_interval,
            max_usage_per_connection=max_usage_per_connection,
        )
        self._pools[name] = pool
        return pool
    
    def get_pool(self, name: str) -> Optional[ConnectionPool]:
        """
        Get a connection pool by name.
        
        Args:
            name: Pool name
            
        Returns:
            ConnectionPool instance or None
        """
        return self._pools.get(name)
    
    async def start_all(self):
        """Start all connection pools."""
        for name, pool in self._pools.items():
            await pool.start()
            logger.info(f"Started connection pool: {name}")
    
    async def stop_all(self):
        """Stop all connection pools."""
        for name, pool in self._pools.items():
            await pool.stop()
            logger.info(f"Stopped connection pool: {name}")
    
    def list_pools(self) -> List[str]:
        """
        List all connection pools.
        
        Returns:
            List of pool names
        """
        return list(self._pools.keys())


# Global connection pool manager
connection_pool_manager = ConnectionPoolManager()
