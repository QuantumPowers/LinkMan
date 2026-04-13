"""Tests for server session manager."""

import pytest
import asyncio

from linkman.server.core.session import Session, SessionManager


class TestSession:
    """Test Session class."""

    def test_session_creation(self):
        session = Session(
            session_id="test-session",
            client_address="192.168.1.1:12345",
        )
        
        assert session.session_id == "test-session"
        assert session.client_address == "192.168.1.1:12345"
        assert session.is_active

    def test_duration(self):
        import time
        
        session = Session(
            session_id="test",
            client_address="client1",
        )
        time.sleep(0.1)
        
        assert session.duration >= 0.1

    def test_total_bytes(self):
        session = Session(
            session_id="test",
            client_address="client1",
        )
        session.bytes_sent = 1000
        session.bytes_received = 500
        
        assert session.total_bytes == 1500

    def test_update_activity(self):
        session = Session(
            session_id="test",
            client_address="client1",
        )
        
        session.update_activity(sent=1000, received=500)
        
        assert session.bytes_sent == 1000
        assert session.bytes_received == 500

    def test_end(self):
        session = Session(
            session_id="test",
            client_address="client1",
        )
        
        session.end()
        
        assert not session.is_active
        assert session.end_time is not None

    def test_to_dict(self):
        session = Session(
            session_id="test",
            client_address="client1",
            device_id="device1",
        )
        
        data = session.to_dict()
        
        assert data["session_id"] == "test"
        assert data["client_address"] == "client1"
        assert data["device_id"] == "device1"
        assert data["is_active"] is True


class TestSessionManager:
    """Test SessionManager class."""

    @pytest.fixture
    def manager(self):
        return SessionManager(session_timeout=60)

    @pytest.mark.asyncio
    async def test_start_stop(self, manager):
        await manager.start()
        
        assert manager._running
        
        await manager.stop()
        
        assert not manager._running

    @pytest.mark.asyncio
    async def test_create_session(self, manager):
        await manager.start()
        
        session = manager.create_session(
            client_address="192.168.1.1:12345",
            device_id="device1",
        )
        
        assert session is not None
        assert session.client_address == "192.168.1.1:12345"
        assert manager._sessions.get(session.session_id) == session
        
        await manager.stop()

    @pytest.mark.asyncio
    async def test_get_session(self, manager):
        await manager.start()
        
        session = manager.create_session("client1")
        
        retrieved = manager.get_session(session.session_id)
        
        assert retrieved == session
        
        await manager.stop()

    @pytest.mark.asyncio
    async def test_get_client_sessions(self, manager):
        await manager.start()
        
        manager.create_session("client1")
        manager.create_session("client1")
        manager.create_session("client2")
        
        sessions = manager.get_client_sessions("client1")
        
        assert len(sessions) == 2
        
        await manager.stop()

    @pytest.mark.asyncio
    async def test_get_active_sessions(self, manager):
        await manager.start()
        
        session1 = manager.create_session("client1")
        session2 = manager.create_session("client2")
        session2.end()
        
        active = manager.get_active_sessions()
        
        assert len(active) == 1
        assert active[0].session_id == session1.session_id
        
        await manager.stop()

    @pytest.mark.asyncio
    async def test_update_session(self, manager):
        await manager.start()
        
        session = manager.create_session("client1")
        
        manager.update_session(session.session_id, sent=1000, received=500)
        
        assert session.bytes_sent == 1000
        assert session.bytes_received == 500
        
        await manager.stop()

    @pytest.mark.asyncio
    async def test_end_session(self, manager):
        await manager.start()
        
        manager.create_session("client1")
        
        await manager.end_session("client1")
        
        sessions = manager.get_client_sessions("client1")
        assert all(not s.is_active for s in sessions)
        
        await manager.stop()

    @pytest.mark.asyncio
    async def test_get_stats(self, manager):
        await manager.start()
        
        manager.create_session("client1")
        manager.create_session("client2")
        
        stats = manager.get_stats()
        
        assert stats["total_sessions"] == 2
        assert stats["active_sessions"] == 2
        assert stats["unique_clients"] == 2
        
        await manager.stop()

    def test_from_config(self):
        config = {
            "session_timeout": 120,
            "max_sessions": 5000,
        }
        
        manager = SessionManager.from_config(config)
        
        assert manager._session_timeout == 120
        assert manager._max_sessions == 5000
