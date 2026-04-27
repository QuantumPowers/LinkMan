"""
REST API routes for server management.

Provides:
- Status endpoints
- Device management
- Traffic statistics
- Configuration
- Rate limiting
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

if TYPE_CHECKING:
    from linkman.server.core.handler import ConnectionHandler
    from linkman.server.core.session import SessionManager
    from linkman.server.manager.device import DeviceManager
    from linkman.server.manager.traffic import TrafficManager
    from linkman.server.manager.monitor import Monitor


class RateLimiter:
    """Simple in-memory token bucket rate limiter."""

    def __init__(self, requests_per_minute: int = 60):
        self._rate = requests_per_minute
        self._window = 60.0
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, client_ip: str, now: float) -> None:
        window_start = now - self._window
        self._buckets[client_ip] = [
            t for t in self._buckets[client_ip] if t > window_start
        ]
        if not self._buckets[client_ip]:
            del self._buckets[client_ip]

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        self._cleanup(client_ip, now)
        if len(self._buckets.get(client_ip, [])) >= self._rate:
            return False
        self._buckets[client_ip].append(now)
        return True


_rate_limiter = RateLimiter(requests_per_minute=120)


class StatusResponse(BaseModel):
    status: str
    uptime: float
    uptime_str: str
    connections: int
    total_connections: int
    cpu_percent: float
    memory_percent: float


class TrafficResponse(BaseModel):
    total_mb: float
    total_gb: float
    limit_mb: int
    remaining_mb: float
    client_count: int


class DeviceResponse(BaseModel):
    device_id: str
    name: str
    status: str
    last_seen: float
    total_bytes: int


class DeviceListResponse(BaseModel):
    total: int
    online: int
    devices: list[DeviceResponse]


class ConfigUpdateRequest(BaseModel):
    key: str
    value: str


def create_app(
    connection_handler: "ConnectionHandler | None" = None,
    session_manager: "SessionManager | None" = None,
    device_manager: "DeviceManager | None" = None,
    traffic_manager: "TrafficManager | None" = None,
    monitor: "Monitor | None" = None,
) -> FastAPI:
    app = FastAPI(
        title="LinkMan Server API",
        description="Management API for LinkMan VPN Server",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    )

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        if path.startswith("/api/") and not _rate_limiter.is_allowed(client_ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
            )
        return await call_next(request)

    @app.get("/", tags=["Root"])
    async def root():
        return {
            "name": "LinkMan Server",
            "version": "1.0.0",
            "status": "running",
        }

    @app.get("/api/status", response_model=StatusResponse, tags=["Status"])
    async def get_status():
        if not monitor:
            raise HTTPException(status_code=503, detail="Monitor not available")

        status = monitor.status
        return StatusResponse(
            status="running",
            uptime=status.uptime,
            uptime_str=status.uptime_str,
            connections=status.connections,
            total_connections=status.total_connections,
            cpu_percent=status.cpu_percent,
            memory_percent=status.memory_percent,
        )

    @app.get("/api/status/full", tags=["Status"])
    async def get_full_status():
        if not monitor:
            raise HTTPException(status_code=503, detail="Monitor not available")

        return monitor.get_full_status()

    @app.get("/api/traffic", response_model=TrafficResponse, tags=["Traffic"])
    async def get_traffic():
        if not traffic_manager:
            raise HTTPException(status_code=503, detail="Traffic manager not available")

        stats = traffic_manager.get_stats()
        return TrafficResponse(
            total_mb=stats["total_mb"],
            total_gb=stats["total_gb"],
            limit_mb=stats["limit_mb"],
            remaining_mb=stats["remaining_mb"],
            client_count=stats["client_count"],
        )

    @app.get("/api/traffic/report", tags=["Traffic"])
    async def get_traffic_report():
        if not traffic_manager:
            raise HTTPException(status_code=503, detail="Traffic manager not available")

        return traffic_manager.get_stats()

    @app.get("/api/traffic/top", tags=["Traffic"])
    async def get_top_clients(limit: int = 10):
        if not traffic_manager:
            raise HTTPException(status_code=503, detail="Traffic manager not available")

        if limit < 1 or limit > 100:
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")

        top = traffic_manager.get_top_clients(limit)
        return [
            {
                "client_id": cid,
                "total_mb": round(stats.total_mb, 2),
                "total_gb": round(stats.total_gb, 3),
            }
            for cid, stats in top
        ]

    @app.get("/api/devices", response_model=DeviceListResponse, tags=["Devices"])
    async def get_devices():
        if not device_manager:
            raise HTTPException(status_code=503, detail="Device manager not available")

        devices = device_manager.get_all_devices()
        return DeviceListResponse(
            total=device_manager.device_count,
            online=device_manager.online_count,
            devices=[
                DeviceResponse(
                    device_id=d.device_id,
                    name=d.name,
                    status=d.status.value,
                    last_seen=d.last_seen,
                    total_bytes=d.total_bytes,
                )
                for d in devices
            ],
        )

    @app.get("/api/devices/{device_id}", tags=["Devices"])
    async def get_device(device_id: str):
        if not device_manager:
            raise HTTPException(status_code=503, detail="Device manager not available")

        if not device_id or len(device_id) > 50 or not device_id.isalnum():
            raise HTTPException(status_code=400, detail="Invalid device ID format. Must be alphanumeric and less than 50 characters.")

        device = device_manager.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        return device.to_dict()

    @app.delete("/api/devices/{device_id}", tags=["Devices"])
    async def remove_device(device_id: str):
        if not device_manager:
            raise HTTPException(status_code=503, detail="Device manager not available")

        if not device_id or len(device_id) > 50 or not device_id.isalnum():
            raise HTTPException(status_code=400, detail="Invalid device ID format. Must be alphanumeric and less than 50 characters.")

        if not device_manager.unregister_device(device_id):
            raise HTTPException(status_code=404, detail="Device not found")

        return {"status": "removed", "device_id": device_id}

    @app.get("/api/sessions", tags=["Sessions"])
    async def get_sessions():
        if not session_manager:
            raise HTTPException(status_code=503, detail="Session manager not available")

        sessions = session_manager.get_active_sessions()
        return {
            "total": len(sessions),
            "sessions": [s.to_dict() for s in sessions],
        }

    @app.get("/api/sessions/stats", tags=["Sessions"])
    async def get_session_stats():
        if not session_manager:
            raise HTTPException(status_code=503, detail="Session manager not available")

        return session_manager.get_stats()

    @app.get("/api/connections", tags=["Connections"])
    async def get_connections():
        if not connection_handler:
            raise HTTPException(status_code=503, detail="Connection handler not available")

        return connection_handler.get_stats()

    return app
