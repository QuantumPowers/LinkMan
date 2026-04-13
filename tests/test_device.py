"""Tests for server device manager."""

import pytest

from linkman.server.manager.device import Device, DeviceManager, DeviceStatus


class TestDevice:
    """Test Device class."""

    def test_device_creation(self):
        device = Device(
            device_id="test123",
            name="Test Device",
        )
        
        assert device.device_id == "test123"
        assert device.name == "Test Device"
        assert device.status == DeviceStatus.OFFLINE

    def test_is_online(self):
        device = Device(device_id="test", name="Test")
        
        assert not device.is_online
        
        device.status = DeviceStatus.ONLINE
        
        assert device.is_online

    def test_update_activity(self):
        device = Device(device_id="test", name="Test")
        initial_bytes = device.total_bytes
        
        device.update_activity(bytes_transferred=1000)
        
        assert device.total_bytes == initial_bytes + 1000

    def test_to_dict(self):
        device = Device(
            device_id="test",
            name="Test Device",
            user_id="user1",
        )
        
        data = device.to_dict()
        
        assert data["device_id"] == "test"
        assert data["name"] == "Test Device"
        assert data["user_id"] == "user1"


class TestDeviceManager:
    """Test DeviceManager class."""

    @pytest.fixture
    def manager(self):
        return DeviceManager(max_devices=3)

    def test_initial_state(self, manager):
        assert manager.device_count == 0
        assert manager.online_count == 0

    def test_register_device(self, manager):
        device = manager.register_device("device1", "My Device")
        
        assert device is not None
        assert device.device_id == "device1"
        assert device.name == "My Device"
        assert device.status == DeviceStatus.ONLINE
        assert manager.device_count == 1

    def test_register_device_limit(self, manager):
        manager.register_device("device1", "Device 1")
        manager.register_device("device2", "Device 2")
        manager.register_device("device3", "Device 3")
        
        device4 = manager.register_device("device4", "Device 4")
        
        assert device4 is None
        assert manager.device_count == 3

    def test_unregister_device(self, manager):
        manager.register_device("device1", "Device 1")
        
        result = manager.unregister_device("device1")
        
        assert result is True
        assert manager.device_count == 0

    def test_unregister_nonexistent(self, manager):
        result = manager.unregister_device("nonexistent")
        
        assert result is False

    def test_get_device(self, manager):
        manager.register_device("device1", "Device 1")
        
        device = manager.get_device("device1")
        
        assert device is not None
        assert device.name == "Device 1"

    def test_get_all_devices(self, manager):
        manager.register_device("device1", "Device 1")
        manager.register_device("device2", "Device 2")
        
        devices = manager.get_all_devices()
        
        assert len(devices) == 2

    def test_get_online_devices(self, manager):
        device1 = manager.register_device("device1", "Device 1")
        device2 = manager.register_device("device2", "Device 2")
        device2.status = DeviceStatus.OFFLINE
        
        online = manager.get_online_devices()
        
        assert len(online) == 1
        assert online[0].device_id == "device1"

    def test_device_connect_disconnect(self, manager):
        manager.register_device("device1", "Device 1")
        
        manager.device_connect("device1")
        
        device = manager.get_device("device1")
        assert device.connection_count == 1
        
        manager.device_disconnect("device1")
        
        assert device.status == DeviceStatus.IDLE

    def test_is_device_allowed(self, manager):
        manager.register_device("device1", "Device 1")
        
        assert manager.is_device_allowed("device1")
        assert manager.is_device_allowed("device2")
        
        manager.register_device("device2", "Device 2")
        manager.register_device("device3", "Device 3")
        
        assert not manager.is_device_allowed("device4")

    def test_update_device_activity(self, manager):
        manager.register_device("device1", "Device 1")
        
        manager.update_device_activity("device1", bytes_transferred=1000)
        
        device = manager.get_device("device1")
        assert device.total_bytes == 1000

    def test_get_stats(self, manager):
        manager.register_device("device1", "Device 1")
        manager.register_device("device2", "Device 2")
        
        stats = manager.get_stats()
        
        assert stats["total_devices"] == 2
        assert stats["max_devices"] == 3

    def test_pre_allowed_devices(self):
        manager = DeviceManager(
            max_devices=5,
            allowed_devices=["pre-allowed-1", "pre-allowed-2"],
        )
        
        assert manager.device_count == 2

    def test_generate_device_id(self):
        device_id = DeviceManager.generate_device_id("user@example.com")
        
        assert len(device_id) == 16
        
        same_id = DeviceManager.generate_device_id("user@example.com")
        assert device_id == same_id
