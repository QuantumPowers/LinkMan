"""Tests for connection pool module."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock

from linkman.shared.utils.connection_pool import ConnectionPool


class TestConnectionPool:
    """Test ConnectionPool."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create a mock connection
        self.mock_reader = Mock()
        self.mock_reader.at_eof = Mock(return_value=False)
        
        self.mock_writer = Mock()
        self.mock_transport = Mock()
        self.mock_transport.is_closing = Mock(return_value=False)
        self.mock_transport.set_read_timeout = Mock()
        self.mock_writer.transport = self.mock_transport
        self.mock_writer.close = AsyncMock()
        self.mock_writer.wait_closed = AsyncMock()
        
        # Create a mock connection factory
        async def mock_create_connection():
            return self.mock_reader, self.mock_writer
        
        self.create_connection = mock_create_connection
        
        # Create connection pool
        self.pool = ConnectionPool(
            create_connection=self.create_connection,
            max_connections=5,
            max_idle_time=10.0,
            health_check_interval=5.0,
            max_usage_per_connection=10,
        )

    async def teardown_method(self):
        """Tear down test fixtures."""
        if self.pool._running:
            await self.pool.stop()

    async def test_get_connection(self):
        """Test get_connection method."""
        await self.pool.start()
        
        # Get a connection
        conn = await self.pool.get_connection()
        assert conn is not None
        assert conn.reader == self.mock_reader
        assert conn.writer == self.mock_writer
        assert self.pool.active_connections == 1
        
        # Return the connection
        await self.pool.return_connection(conn)
        assert self.pool.active_connections == 0
        assert self.pool.available_connections == 1

    async def test_get_connection_timeout(self):
        """Test get_connection with timeout."""
        await self.pool.start()
        
        # Fill the pool
        connections = []
        for _ in range(5):
            conn = await self.pool.get_connection()
            connections.append(conn)
        
        # Try to get another connection with short timeout
        with pytest.raises(TimeoutError):
            await self.pool.get_connection(timeout=0.1)
        
        # Return a connection
        await self.pool.return_connection(connections[0])
        
        # Now we should be able to get a connection
        conn = await self.pool.get_connection(timeout=1.0)
        assert conn is not None
        
        # Return all connections
        for conn in connections[1:]:
            await self.pool.return_connection(conn)
        await self.pool.return_connection(conn)

    async def test_health_check(self):
        """Test connection health check."""
        await self.pool.start()
        
        # Get and return a connection
        conn = await self.pool.get_connection()
        await self.pool.return_connection(conn)
        
        # Wait for health check to run
        await asyncio.sleep(0.1)
        
        # Connection should still be healthy
        assert conn.is_healthy is True
        
        # Make the connection appear unhealthy
        self.mock_transport.is_closing = Mock(return_value=True)
        
        # Run health check
        await self.pool._check_connections_health()
        
        # Connection should now be marked as unhealthy
        assert conn.is_healthy is False

    async def test_cleanup_idle_connections(self):
        """Test cleanup of idle connections."""
        await self.pool.start()
        
        # Get and return a connection
        conn = await self.pool.get_connection()
        await self.pool.return_connection(conn)
        
        # Manually set last_used to a time in the past
        conn.last_used = 0  # Very old
        
        # Run cleanup
        await self.pool._cleanup_idle_connections()
        
        # Connection should be removed
        assert self.pool.total_connections == 0

    async def test_max_usage_per_connection(self):
        """Test max usage per connection."""
        await self.pool.start()
        
        # Get a connection
        conn = await self.pool.get_connection()
        
        # Manually set usage count to max
        conn.usage_count = 10
        
        # Return the connection
        await self.pool.return_connection(conn)
        
        # Connection should be removed
        assert self.pool.total_connections == 0

    async def test_connection_age_check(self):
        """Test connection age check in health check."""
        await self.pool.start()
        
        # Get and return a connection
        conn = await self.pool.get_connection()
        await self.pool.return_connection(conn)
        
        # Manually set created_at to a time in the past (2 hours ago)
        import time
        conn.created_at = time.time() - 7200  # 2 hours
        
        # Run health check
        await self.pool._check_connections_health()
        
        # Connection should be marked as unhealthy
        assert conn.is_healthy is False

    async def test_idle_time_check(self):
        """Test idle time check in health check."""
        await self.pool.start()
        
        # Get and return a connection
        conn = await self.pool.get_connection()
        await self.pool.return_connection(conn)
        
        # Manually set last_used to a time in the past (just over 80% of max idle time)
        import time
        conn.last_used = time.time() - (self.pool._max_idle_time * 0.9)  # 90% of max idle time
        
        # Run health check
        await self.pool._check_connections_health()
        
        # Connection should be marked as unhealthy
        assert conn.is_healthy is False
