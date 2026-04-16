"""
Monitoring utilities for LinkMan VPN.

Provides metrics collection, storage, and analysis for system monitoring.
"""

from __future__ import annotations

import asyncio
import time
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Callable
from pathlib import Path

from linkman.shared.utils.logger import get_logger

logger = get_logger("utils.monitoring")


@dataclass
class Metric:
    """Metric data."""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """
    Metrics collector for gathering system and application metrics.
    
    Features:
    - Collect system metrics (CPU, memory, network)
    - Collect application metrics (connections, traffic, latency)
    - Aggregate metrics
    - Export metrics in various formats
    """
    
    def __init__(self, collect_interval: float = 10.0):
        """
        Initialize metrics collector.
        
        Args:
            collect_interval: Interval between metric collection
        """
        self._collect_interval = collect_interval
        self._metrics: Dict[str, List[Metric]] = {}
        self._collect_tasks: List[asyncio.Task] = []
        self._running = False
        self._export_callbacks: List[Callable[[Dict[str, List[Metric]], float], None]] = []
    
    async def start(self):
        """Start the metrics collector."""
        if not self._running:
            self._running = True
            self._collect_tasks.append(asyncio.create_task(self._collect_system_metrics()))
            self._collect_tasks.append(asyncio.create_task(self._collect_application_metrics()))
            self._collect_tasks.append(asyncio.create_task(self._export_metrics()))
            logger.info("Metrics collector started")
    
    async def stop(self):
        """Stop the metrics collector."""
        if self._running:
            self._running = False
            for task in self._collect_tasks:
                task.cancel()
            self._collect_tasks.clear()
            logger.info("Metrics collector stopped")
    
    def add_metric(self, name: str, value: float, **tags):
        """
        Add a metric.
        
        Args:
            name: Metric name
            value: Metric value
            **tags: Metric tags
        """
        metric = Metric(name=name, value=value, tags=tags)
        if name not in self._metrics:
            self._metrics[name] = []
        self._metrics[name].append(metric)
        
        # Keep only last 1000 metrics per metric name
        if len(self._metrics[name]) > 1000:
            self._metrics[name] = self._metrics[name][-1000:]
    
    def get_metrics(self, name: str | None = None) -> Dict[str, List[Metric]]:
        """
        Get metrics.
        
        Args:
            name: Optional metric name
            
        Returns:
            Dict of metric name to list of metrics
        """
        if name:
            return {name: self._metrics.get(name, [])}
        return self._metrics
    
    def clear_metrics(self, name: str | None = None):
        """
        Clear metrics.
        
        Args:
            name: Optional metric name
        """
        if name:
            if name in self._metrics:
                del self._metrics[name]
        else:
            self._metrics.clear()
    
    def add_export_callback(self, callback: Callable[[Dict[str, List[Metric]], float], None]):
        """
        Add an export callback.
        
        Args:
            callback: Callback function to call when exporting metrics
        """
        self._export_callbacks.append(callback)
    
    async def _collect_system_metrics(self):
        """Collect system metrics."""
        while self._running:
            try:
                # Collect CPU usage
                import psutil
                cpu_percent = psutil.cpu_percent(interval=1)
                self.add_metric("system.cpu.percent", cpu_percent)
                
                # Collect memory usage
                memory = psutil.virtual_memory()
                self.add_metric("system.memory.percent", memory.percent)
                self.add_metric("system.memory.used", memory.used / (1024 * 1024))  # MB
                self.add_metric("system.memory.available", memory.available / (1024 * 1024))  # MB
                
                # Collect network usage
                net_io = psutil.net_io_counters()
                self.add_metric("system.network.bytes_sent", net_io.bytes_sent)
                self.add_metric("system.network.bytes_recv", net_io.bytes_recv)
                
            except ImportError:
                # psutil not installed, skip system metrics
                break
            except Exception as e:
                logger.error(f"Error collecting system metrics: {e}")
            
            await asyncio.sleep(self._collect_interval)
    
    async def _collect_application_metrics(self):
        """Collect application metrics."""
        while self._running:
            try:
                # Application-specific metrics will be added by other components
                # This is a placeholder for now
                pass
            except Exception as e:
                logger.error(f"Error collecting application metrics: {e}")
            
            await asyncio.sleep(self._collect_interval)
    
    async def _export_metrics(self):
        """Export metrics periodically."""
        while self._running:
            try:
                timestamp = time.time()
                for callback in self._export_callbacks:
                    try:
                        callback(self._metrics, timestamp)
                    except Exception as e:
                        logger.error(f"Error in export callback: {e}")
            except Exception as e:
                logger.error(f"Error exporting metrics: {e}")
            
            await asyncio.sleep(self._collect_interval * 6)


class MetricsExporter:
    """
    Metrics exporter for exporting metrics to various destinations.
    
    Supports exporting to:
    - JSON files
    - Prometheus
    - InfluxDB
    - Custom destinations
    """
    
    def __init__(self, collector: MetricsCollector):
        """
        Initialize metrics exporter.
        
        Args:
            collector: Metrics collector instance
        """
        self._collector = collector
        self._collector.add_export_callback(self.export)
    
    def export(self, metrics: Dict[str, List[Metric]], timestamp: float):
        """
        Export metrics.
        
        Args:
            metrics: Metrics to export
            timestamp: Export timestamp
        """
        # Base class, to be overridden by subclasses
        pass


class JSONMetricsExporter(MetricsExporter):
    """Metrics exporter for JSON files."""
    
    def __init__(self, collector: MetricsCollector, export_dir: str = "./metrics"):
        """
        Initialize JSON metrics exporter.
        
        Args:
            collector: Metrics collector instance
            export_dir: Export directory
        """
        super().__init__(collector)
        self._export_dir = Path(export_dir)
        self._export_dir.mkdir(parents=True, exist_ok=True)
    
    def export(self, metrics: Dict[str, List[Metric]], timestamp: float):
        """
        Export metrics to JSON file.
        
        Args:
            metrics: Metrics to export
            timestamp: Export timestamp
        """
        try:
            export_data = {
                "timestamp": timestamp,
                "metrics": {}
            }
            
            for metric_name, metric_list in metrics.items():
                export_data["metrics"][metric_name] = [
                    {
                        "value": metric.value,
                        "timestamp": metric.timestamp,
                        "tags": metric.tags
                    }
                    for metric in metric_list
                ]
            
            export_file = self._export_dir / f"metrics_{int(timestamp)}.json"
            with open(export_file, "w") as f:
                json.dump(export_data, f, indent=2)
            
            # Clean up old files (keep last 10)
            files = sorted(self._export_dir.glob("metrics_*.json"), key=lambda x: x.stat().st_mtime)
            if len(files) > 10:
                for file in files[:-10]:
                    file.unlink()
        except Exception as e:
            logger.error(f"Error exporting metrics to JSON: {e}")


class AlertManager:
    """
    Alert manager for monitoring thresholds and sending alerts.
    
    Features:
    - Threshold-based alerts
    - Alert history
    - Alert notification
    """
    
    @dataclass
    class Alert:
        """Alert data."""
        name: str
        message: str
        severity: str  # info, warning, error, critical
        timestamp: float = field(default_factory=time.time)
        tags: Dict[str, str] = field(default_factory=dict)
    
    @dataclass
    class Threshold:
        """Alert threshold."""
        metric_name: str
        operator: str  # >, <, >=, <=, ==
        value: float
        severity: str
        message: str
        check_interval: float = 60.0
        cooldown: float = 300.0  # 5 minutes
        last_triggered: float = 0.0
    
    def __init__(self, collector: MetricsCollector):
        """
        Initialize alert manager.
        
        Args:
            collector: Metrics collector instance
        """
        self._collector = collector
        self._thresholds: List[AlertManager.Threshold] = []
        self._alerts: List[AlertManager.Alert] = []
        self._alert_callbacks: List[Callable[[AlertManager.Alert], None]] = []
        self._check_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        """Start the alert manager."""
        if not self._running:
            self._running = True
            self._check_task = asyncio.create_task(self._check_thresholds())
            logger.info("Alert manager started")
    
    async def stop(self):
        """
        Stop the alert manager.
        """
        if self._running:
            self._running = False
            if self._check_task:
                self._check_task.cancel()
            logger.info("Alert manager stopped")
    
    def add_threshold(self, threshold: Threshold):
        """
        Add an alert threshold.
        
        Args:
            threshold: Alert threshold
        """
        self._thresholds.append(threshold)
    
    def add_alert_callback(self, callback: Callable[[Alert], None]):
        """
        Add an alert callback.
        
        Args:
            callback: Callback function to call when an alert is triggered
        """
        self._alert_callbacks.append(callback)
    
    def get_alerts(self, severity: str | None = None) -> List[Alert]:
        """
        Get alerts.
        
        Args:
            severity: Optional severity filter
            
        Returns:
            List of alerts
        """
        if severity:
            return [alert for alert in self._alerts if alert.severity == severity]
        return self._alerts
    
    def clear_alerts(self):
        """
        Clear all alerts.
        """
        self._alerts.clear()
    
    async def _check_thresholds(self):
        """
        Check thresholds periodically.
        """
        while self._running:
            try:
                now = time.time()
                metrics = self._collector.get_metrics()
                
                for threshold in self._thresholds:
                    # Check if metric exists
                    if threshold.metric_name not in metrics:
                        continue
                    
                    # Get latest metric value
                    metric_list = metrics[threshold.metric_name]
                    if not metric_list:
                        continue
                    
                    latest_metric = metric_list[-1]
                    
                    # Check if threshold is triggered
                    triggered = False
                    if threshold.operator == ">":
                        triggered = latest_metric.value > threshold.value
                    elif threshold.operator == "<":
                        triggered = latest_metric.value < threshold.value
                    elif threshold.operator == ">=":
                        triggered = latest_metric.value >= threshold.value
                    elif threshold.operator == "<=":
                        triggered = latest_metric.value <= threshold.value
                    elif threshold.operator == "==":
                        triggered = latest_metric.value == threshold.value
                    
                    # Check cooldown
                    if triggered and now - threshold.last_triggered > threshold.cooldown:
                        # Trigger alert
                        alert = AlertManager.Alert(
                            name=threshold.metric_name,
                            message=threshold.message,
                            severity=threshold.severity,
                            tags=latest_metric.tags
                        )
                        self._alerts.append(alert)
                        threshold.last_triggered = now
                        
                        # Notify callbacks
                        for callback in self._alert_callbacks:
                            try:
                                callback(alert)
                            except Exception as e:
                                logger.error(f"Error in alert callback: {e}")
                        
                        logger.warning(f"Alert triggered: {alert.message} (Severity: {alert.severity})")
                        
            except Exception as e:
                logger.error(f"Error checking thresholds: {e}")
            
            await asyncio.sleep(10.0)  # Check every 10 seconds


class MonitoringManager:
    """
    Manager for monitoring components.
    
    Coordinates metrics collection, export, and alerting.
    """
    
    def __init__(self):
        """
        Initialize monitoring manager.
        """
        self._collector = MetricsCollector()
        self._exporters: List[MetricsExporter] = []
        self._alert_manager = AlertManager(self._collector)
    
    def get_collector(self) -> MetricsCollector:
        """
        Get metrics collector.
        
        Returns:
            MetricsCollector instance
        """
        return self._collector
    
    def get_alert_manager(self) -> AlertManager:
        """
        Get alert manager.
        
        Returns:
            AlertManager instance
        """
        return self._alert_manager
    
    def add_exporter(self, exporter: MetricsExporter):
        """
        Add a metrics exporter.
        
        Args:
            exporter: Metrics exporter instance
        """
        self._exporters.append(exporter)
    
    async def start(self):
        """
        Start all monitoring components.
        """
        await self._collector.start()
        await self._alert_manager.start()
        logger.info("Monitoring manager started")
    
    async def stop(self):
        """
        Stop all monitoring components.
        """
        await self._collector.stop()
        await self._alert_manager.stop()
        logger.info("Monitoring manager stopped")


# Global monitoring manager
monitoring_manager = MonitoringManager()


def get_monitoring_manager() -> MonitoringManager:
    """
    Get the global monitoring manager instance.
    
    Returns:
        MonitoringManager instance
    """
    return monitoring_manager
