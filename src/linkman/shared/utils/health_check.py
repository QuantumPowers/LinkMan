"""
Health check utilities for LinkMan VPN.

Provides health checking for servers and services.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable

from linkman.shared.utils.logger import get_logger

logger = get_logger("utils.health_check")


@dataclass
class HealthCheckResult:
    """Health check result."""
    is_healthy: bool
    response_time: float
    timestamp: float = field(default_factory=time.time)
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class ServerHealthStatus:
    """Server health status."""
    host: str
    port: int
    is_healthy: bool
    last_check: float
    response_time: float
    consecutive_failures: int
    status_history: List[HealthCheckResult] = field(default_factory=list)


class HealthChecker:
    """
    Health checker for servers and services.
    
    Features:
    - TCP connectivity checks
    - HTTP/HTTPS health checks
    - Custom health check functions
    - Health status tracking
    - Alerting
    """
    
    def __init__(
        self,
        check_interval: float = 30.0,  # 30 seconds
        timeout: float = 5.0,  # 5 seconds
        max_consecutive_failures: int = 3,
    ):
        """
        Initialize health checker.
        
        Args:
            check_interval: Interval between health checks
            timeout: Timeout for each health check
            max_consecutive_failures: Maximum consecutive failures before marking as unhealthy
        """
        self._check_interval = check_interval
        self._timeout = timeout
        self._max_consecutive_failures = max_consecutive_failures
        
        self._servers: Dict[str, ServerHealthStatus] = {}
        self._check_tasks: Dict[str, asyncio.Task] = {}
        self._alert_callbacks: List[Callable[[str, ServerHealthStatus], None]] = []
        self._running = False
    
    async def start(self):
        """Start the health checker."""
        if not self._running:
            self._running = True
            logger.info("Health checker started")
    
    async def stop(self):
        """Stop the health checker."""
        if self._running:
            self._running = False
            
            # Cancel all check tasks
            for task in self._check_tasks.values():
                task.cancel()
            
            self._check_tasks.clear()
            logger.info("Health checker stopped")
    
    def add_server(self, host: str, port: int, check_type: str = "tcp"):
        """
        Add a server to monitor.
        
        Args:
            host: Server hostname or IP
            port: Server port
            check_type: Check type (tcp, http, https, custom)
        """
        server_id = f"{host}:{port}"
        if server_id not in self._servers:
            self._servers[server_id] = ServerHealthStatus(
                host=host,
                port=port,
                is_healthy=True,
                last_check=0.0,
                response_time=0.0,
                consecutive_failures=0,
            )
            
            # Start health check task
            task = asyncio.create_task(self._check_server_health(server_id, check_type))
            self._check_tasks[server_id] = task
            logger.info(f"Added server {server_id} for health monitoring")
    
    def remove_server(self, host: str, port: int):
        """
        Remove a server from monitoring.
        
        Args:
            host: Server hostname or IP
            port: Server port
        """
        server_id = f"{host}:{port}"
        if server_id in self._servers:
            if server_id in self._check_tasks:
                self._check_tasks[server_id].cancel()
                del self._check_tasks[server_id]
            del self._servers[server_id]
            logger.info(f"Removed server {server_id} from health monitoring")
    
    def add_alert_callback(self, callback: Callable[[str, ServerHealthStatus], None]):
        """
        Add an alert callback.
        
        Args:
            callback: Callback function to call when server health status changes
        """
        self._alert_callbacks.append(callback)
    
    def get_server_status(self, host: str, port: int) -> Optional[ServerHealthStatus]:
        """
        Get server health status.
        
        Args:
            host: Server hostname or IP
            port: Server port
            
        Returns:
            ServerHealthStatus or None
        """
        server_id = f"{host}:{port}"
        return self._servers.get(server_id)
    
    def get_all_servers_status(self) -> Dict[str, ServerHealthStatus]:
        """
        Get health status for all servers.
        
        Returns:
            Dict of server ID to ServerHealthStatus
        """
        return self._servers.copy()
    
    async def _check_server_health(self, server_id: str, check_type: str):
        """Check server health periodically."""
        while self._running:
            try:
                status = self._servers.get(server_id)
                if not status:
                    break
                
                start_time = time.time()
                is_healthy = False
                error = None
                
                try:
                    if check_type == "tcp":
                        is_healthy = await self._check_tcp(status.host, status.port)
                    elif check_type == "http":
                        is_healthy = await self._check_http(f"http://{status.host}:{status.port}")
                    elif check_type == "https":
                        is_healthy = await self._check_http(f"https://{status.host}:{status.port}")
                    else:
                        logger.warning(f"Unknown check type: {check_type}")
                        is_healthy = False
                except Exception as e:
                    error = str(e)
                    is_healthy = False
                
                response_time = time.time() - start_time
                
                # Update status
                old_healthy = status.is_healthy
                
                if is_healthy:
                    status.is_healthy = True
                    status.consecutive_failures = 0
                else:
                    status.consecutive_failures += 1
                    if status.consecutive_failures >= self._max_consecutive_failures:
                        status.is_healthy = False
                
                status.last_check = time.time()
                status.response_time = response_time
                
                # Add to history
                result = HealthCheckResult(
                    is_healthy=is_healthy,
                    response_time=response_time,
                    error=error,
                )
                status.status_history.append(result)
                
                # Keep only last 100 results
                if len(status.status_history) > 100:
                    status.status_history = status.status_history[-100:]
                
                # Trigger alert if status changed
                if status.is_healthy != old_healthy:
                    logger.info(f"Server {server_id} health status changed: {old_healthy} -> {status.is_healthy}")
                    for callback in self._alert_callbacks:
                        try:
                            callback(server_id, status)
                        except Exception as e:
                            logger.error(f"Error in alert callback: {e}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error checking server health: {e}")
            
            await asyncio.sleep(self._check_interval)
    
    async def _check_tcp(self, host: str, port: int) -> bool:
        """
        Check TCP connectivity.
        
        Args:
            host: Server hostname or IP
            port: Server port
            
        Returns:
            True if connection successful
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self._timeout
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False
    
    async def _check_http(self, url: str) -> bool:
        """
        Check HTTP/HTTPS health.
        
        Args:
            url: URL to check
            
        Returns:
            True if HTTP status is 200
        """
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=self._timeout) as response:
                    return response.status == 200
        except Exception:
            return False


class HealthCheckManager:
    """
    Manager for health checkers.
    
    Allows managing multiple health checkers for different services.
    """
    
    def __init__(self):
        """Initialize health check manager."""
        self._checkers: Dict[str, HealthChecker] = {}
    
    def create_checker(
        self,
        name: str,
        check_interval: float = 30.0,
        timeout: float = 5.0,
        max_consecutive_failures: int = 3,
    ) -> HealthChecker:
        """
        Create a new health checker.
        
        Args:
            name: Checker name
            check_interval: Interval between health checks
            timeout: Timeout for each health check
            max_consecutive_failures: Maximum consecutive failures before marking as unhealthy
            
        Returns:
            HealthChecker instance
        """
        checker = HealthChecker(
            check_interval=check_interval,
            timeout=timeout,
            max_consecutive_failures=max_consecutive_failures,
        )
        self._checkers[name] = checker
        return checker
    
    def get_checker(self, name: str) -> Optional[HealthChecker]:
        """
        Get a health checker by name.
        
        Args:
            name: Checker name
            
        Returns:
            HealthChecker instance or None
        """
        return self._checkers.get(name)
    
    async def start_all(self):
        """Start all health checkers."""
        for name, checker in self._checkers.items():
            await checker.start()
            logger.info(f"Started health checker: {name}")
    
    async def stop_all(self):
        """Stop all health checkers."""
        for name, checker in self._checkers.items():
            await checker.stop()
            logger.info(f"Stopped health checker: {name}")
    
    def list_checkers(self) -> List[str]:
        """
        List all health checkers.
        
        Returns:
            List of checker names
        """
        return list(self._checkers.keys())


# Global health check manager
health_check_manager = HealthCheckManager()
