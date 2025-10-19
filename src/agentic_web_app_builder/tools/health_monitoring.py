"""Health check and uptime monitoring implementation."""

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

from .monitoring_interfaces import (
    HealthCheckTool, HealthStatus, MonitoringSetup, MonitoringMetrics,
    ErrorEvent, ErrorSeverity
)


logger = logging.getLogger(__name__)


class HealthMonitor(HealthCheckTool):
    """Implementation of health check and uptime monitoring."""
    
    def __init__(self):
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._health_history: Dict[str, List[HealthStatus]] = {}
        self._metrics_cache: Dict[str, MonitoringMetrics] = {}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def start(self) -> None:
        """Start the health monitor service."""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        logger.info("Health monitor started")
    
    async def stop(self) -> None:
        """Stop the health monitor service and cleanup resources."""
        # Cancel all monitoring tasks
        for url, task in self._monitoring_tasks.items():
            if not task.done():
                task.cancel()
                logger.info(f"Cancelled monitoring for {url}")
        
        # Wait for tasks to complete
        if self._monitoring_tasks:
            await asyncio.gather(*self._monitoring_tasks.values(), return_exceptions=True)
        
        # Close HTTP session
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info("Health monitor stopped")
    
    async def check_health(self, url: str, timeout: int = 30) -> HealthStatus:
        """Check the health status of a URL."""
        if not self.session:
            await self.start()
        
        start_time = datetime.utcnow()
        
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                end_time = datetime.utcnow()
                response_time = (end_time - start_time).total_seconds() * 1000
                
                # Determine status based on response code
                if 200 <= response.status < 300:
                    status = "up"
                elif 300 <= response.status < 400:
                    status = "up"  # Redirects are generally OK
                elif response.status == 404:
                    status = "degraded"
                else:
                    status = "down"
                
                health_status = HealthStatus(
                    url=url,
                    status=status,
                    response_time=response_time,
                    status_code=response.status,
                    last_checked=end_time
                )
                
                # Store in history
                if url not in self._health_history:
                    self._health_history[url] = []
                self._health_history[url].append(health_status)
                
                # Keep only last 1000 entries
                if len(self._health_history[url]) > 1000:
                    self._health_history[url] = self._health_history[url][-1000:]
                
                logger.debug(f"Health check for {url}: {status} ({response.status}) in {response_time:.2f}ms")
                return health_status
                
        except asyncio.TimeoutError:
            end_time = datetime.utcnow()
            response_time = (end_time - start_time).total_seconds() * 1000
            
            health_status = HealthStatus(
                url=url,
                status="down",
                response_time=response_time,
                last_checked=end_time,
                error_message="Request timeout"
            )
            
            if url not in self._health_history:
                self._health_history[url] = []
            self._health_history[url].append(health_status)
            
            logger.warning(f"Health check timeout for {url} after {timeout}s")
            return health_status
            
        except Exception as e:
            end_time = datetime.utcnow()
            
            health_status = HealthStatus(
                url=url,
                status="down",
                last_checked=end_time,
                error_message=str(e)
            )
            
            if url not in self._health_history:
                self._health_history[url] = []
            self._health_history[url].append(health_status)
            
            logger.error(f"Health check failed for {url}: {str(e)}")
            return health_status
    
    async def setup_uptime_monitoring(self, config: MonitoringSetup) -> Dict[str, Any]:
        """Set up continuous uptime monitoring for a URL."""
        url = config.url
        
        # Stop existing monitoring if any
        if url in self._monitoring_tasks:
            await self.stop_monitoring(url)
        
        # Start new monitoring task
        task = asyncio.create_task(self._monitor_continuously(config))
        self._monitoring_tasks[url] = task
        
        logger.info(f"Started uptime monitoring for {url} with {config.check_interval}s interval")
        
        return {
            "url": url,
            "monitoring_started": True,
            "check_interval": config.check_interval,
            "timeout": config.timeout,
            "project_id": config.project_id
        }
    
    async def get_uptime_metrics(self, url: str, time_period: timedelta = timedelta(days=1)) -> MonitoringMetrics:
        """Get uptime metrics for a URL over a time period."""
        if url not in self._health_history:
            # No history available, perform a single check
            await self.check_health(url)
        
        history = self._health_history.get(url, [])
        if not history:
            raise ValueError(f"No health check history available for {url}")
        
        # Filter history by time period
        cutoff_time = datetime.utcnow() - time_period
        recent_checks = [check for check in history if check.last_checked >= cutoff_time]
        
        if not recent_checks:
            # Use the most recent check if no checks in time period
            recent_checks = [history[-1]]
        
        # Calculate metrics
        total_checks = len(recent_checks)
        up_checks = len([check for check in recent_checks if check.status == "up"])
        uptime_percentage = (up_checks / total_checks * 100) if total_checks > 0 else 0
        
        # Calculate average response time (only for successful checks)
        response_times = [check.response_time for check in recent_checks 
                         if check.response_time is not None and check.status == "up"]
        average_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        # Count errors
        error_checks = [check for check in recent_checks if check.status in ["down", "degraded"]]
        error_rate = (len(error_checks) / total_checks * 100) if total_checks > 0 else 0
        
        # Convert health check failures to error events
        last_24h_errors = []
        for check in error_checks:
            if check.last_checked >= datetime.utcnow() - timedelta(hours=24):
                error_event = ErrorEvent(
                    id=f"{url}_{check.last_checked.isoformat()}",
                    url=url,
                    error_type="uptime_failure",
                    message=check.error_message or f"Status: {check.status}",
                    timestamp=check.last_checked,
                    severity=ErrorSeverity.HIGH if check.status == "down" else ErrorSeverity.MEDIUM
                )
                last_24h_errors.append(error_event)
        
        metrics = MonitoringMetrics(
            url=url,
            uptime_percentage=uptime_percentage,
            average_response_time=average_response_time,
            error_rate=error_rate,
            total_requests=total_checks,
            error_count=len(error_checks),
            last_24h_errors=last_24h_errors,
            collected_at=datetime.utcnow()
        )
        
        # Cache metrics
        self._metrics_cache[url] = metrics
        
        return metrics
    
    async def stop_monitoring(self, url: str) -> bool:
        """Stop monitoring a URL."""
        if url not in self._monitoring_tasks:
            return False
        
        task = self._monitoring_tasks[url]
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        del self._monitoring_tasks[url]
        logger.info(f"Stopped monitoring for {url}")
        return True
    
    async def _monitor_continuously(self, config: MonitoringSetup) -> None:
        """Continuously monitor a URL at specified intervals."""
        url = config.url
        
        try:
            while True:
                try:
                    # Perform health check
                    health_status = await self.check_health(url, config.timeout)
                    
                    # Log significant status changes
                    if url in self._health_history and len(self._health_history[url]) > 1:
                        previous_status = self._health_history[url][-2].status
                        if health_status.status != previous_status:
                            logger.info(f"Status change for {url}: {previous_status} -> {health_status.status}")
                    
                    # Wait for next check
                    await asyncio.sleep(config.check_interval)
                    
                except asyncio.CancelledError:
                    logger.info(f"Monitoring cancelled for {url}")
                    break
                except Exception as e:
                    logger.error(f"Error in continuous monitoring for {url}: {str(e)}")
                    # Continue monitoring despite errors
                    await asyncio.sleep(config.check_interval)
                    
        except asyncio.CancelledError:
            logger.info(f"Continuous monitoring task cancelled for {url}")
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """Validate health monitoring parameters."""
        url = parameters.get("url")
        if not url:
            return False
        
        # Basic URL validation
        try:
            parsed = urlparse(url)
            return parsed.scheme in ["http", "https"] and parsed.netloc
        except Exception:
            return False
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status for all URLs."""
        return {
            "monitored_urls": list(self._monitoring_tasks.keys()),
            "active_tasks": len([task for task in self._monitoring_tasks.values() if not task.done()]),
            "total_history_entries": sum(len(history) for history in self._health_history.values()),
            "cached_metrics": list(self._metrics_cache.keys())
        }