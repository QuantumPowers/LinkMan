"""Tests for server traffic manager."""

import pytest

from linkman.server.manager.traffic import TrafficManager, TrafficStats, TrafficWarning


class TestTrafficStats:
    """Test TrafficStats class."""

    def test_default_values(self):
        stats = TrafficStats()
        
        assert stats.bytes_sent == 0
        assert stats.bytes_received == 0
        assert stats.total_bytes == 0

    def test_add_traffic(self):
        stats = TrafficStats()
        
        stats.add(sent=1000, received=500)
        
        assert stats.bytes_sent == 1000
        assert stats.bytes_received == 500
        assert stats.total_bytes == 1500

    def test_total_mb_gb(self):
        stats = TrafficStats()
        stats.bytes_sent = 1024 * 1024
        stats.bytes_received = 1024 * 1024
        
        assert stats.total_mb == 2.0
        assert stats.total_gb == pytest.approx(2.0 / 1024)

    def test_to_dict(self):
        stats = TrafficStats()
        stats.bytes_sent = 1000
        stats.bytes_received = 500
        
        data = stats.to_dict()
        
        assert data["bytes_sent"] == 1000
        assert data["bytes_received"] == 500
        assert data["total_bytes"] == 1500


class TestTrafficWarning:
    """Test TrafficWarning class."""

    def test_warning_creation(self):
        warning = TrafficWarning(
            threshold_mb=1000,
            current_mb=1200.5,
        )
        
        assert warning.threshold_mb == 1000
        assert warning.current_mb == 1200.5
        assert warning.notified is False


class TestTrafficManager:
    """Test TrafficManager class."""

    @pytest.fixture
    def manager(self):
        return TrafficManager(
            enabled=True,
            limit_mb=1000,
            warning_threshold_mb=800,
        )

    def test_initial_state(self, manager):
        assert manager.total_mb == 0.0
        assert manager.remaining_mb == 1000.0

    def test_record_transfer(self, manager):
        import asyncio
        
        async def test():
            await manager.record_transfer("client1", sent=1024 * 1024, received=512 * 1024)
            
            assert manager.total_mb == pytest.approx(1.5)
        
        asyncio.run(test())

    def test_check_quota_unlimited(self):
        manager = TrafficManager(enabled=True, limit_mb=0)
        
        import asyncio
        
        async def test():
            result = await manager.check_quota("client1")
            assert result is True
        
        asyncio.run(test())

    def test_check_quota_limited(self, manager):
        import asyncio
        
        async def test():
            result = await manager.check_quota("client1")
            assert result is True
            
            for _ in range(200):
                await manager.record_transfer("client1", sent=1024 * 1024 * 5, received=0)
            
            result = await manager.check_quota("client1")
            assert result is False
        
        asyncio.run(test())

    def test_get_client_stats(self, manager):
        import asyncio
        
        async def test():
            await manager.record_transfer("client1", sent=1000, received=500)
            
            stats = manager.get_client_stats("client1")
            
            assert stats.bytes_sent == 1000
            assert stats.bytes_received == 500
        
        asyncio.run(test())

    def test_get_top_clients(self, manager):
        import asyncio
        
        async def test():
            await manager.record_transfer("client1", sent=10000, received=0)
            await manager.record_transfer("client2", sent=5000, received=0)
            await manager.record_transfer("client3", sent=20000, received=0)
            
            top = manager.get_top_clients(limit=2)
            
            assert len(top) == 2
            assert top[0][0] == "client3"
            assert top[1][0] == "client1"
        
        asyncio.run(test())

    def test_reset_stats(self, manager):
        import asyncio
        
        async def test():
            await manager.record_transfer("client1", sent=1000, received=500)
            
            manager.reset_stats()
            
            assert manager.total_mb == 0.0
        
        asyncio.run(test())

    def test_get_stats(self, manager):
        stats = manager.get_stats()
        
        assert stats["enabled"] is True
        assert stats["limit_mb"] == 1000
        assert stats["remaining_mb"] == 1000.0

    def test_disabled_manager(self):
        manager = TrafficManager(enabled=False)
        
        import asyncio
        
        async def test():
            await manager.record_transfer("client1", sent=1000, received=500)
            
            assert manager.total_mb == 0.0
        
        asyncio.run(test())

    def test_warning_callback(self, manager):
        import asyncio
        
        warnings_received = []
        
        async def callback(warning):
            warnings_received.append(warning)
        
        manager.add_warning_callback(callback)
        
        async def test():
            for _ in range(100):
                await manager.record_transfer("client1", sent=1024 * 1024 * 10, received=0)
            
            assert len(warnings_received) > 0
        
        asyncio.run(test())
