"""Monitoring tool interfaces and data models."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field

from ..core.interfaces import ToolInterface


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types of alerts that can be generated."""
    ERROR = "error"
    UPTIME = "uptime"
    PERFORMANCE = "performance"
    SECURITY = "security"
    CUSTOM = "custom"


class NotificationChannel(Enum):
    """Available notification channels."""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    SMS = "sms"


class HealthStatus(BaseModel):
    """Health status of an application."""
    
    url: str = Field(..., description="URL being monitored")
    status: str = Field(..., description="Current status (up, down, degraded)")
    response_time: Optional[float] = Field(None, description="Response time in milliseconds")
    status_code: Optional[int] = Field(None, description="HTTP status code")
    last_checked: datetime = Field(default_factory=datetime.utcnow)
    uptime_percentage: Optional[float] = Field(None, description="Uptime percentage over time period")
    error_message: Optional[str] = Field(None, description="Error message if status is down")


class ErrorEvent(BaseModel):
    """Model for error events detected by monitoring."""
    
    id: str = Field(..., description="Unique error event ID")
    url: str = Field(..., description="URL where error occurred")
    error_type: str = Field(..., description="Type of error (404, 500, js_error, etc.)")
    message: str = Field(..., description="Error message")
    stack_trace: Optional[str] = Field(None, description="Stack trace if available")
    user_agent: Optional[str] = Field(None, description="User agent string")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    severity: ErrorSeverity = Field(default=ErrorSeverity.MEDIUM)
    count: int = Field(default=1, description="Number of times this error occurred")
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    resolved: bool = Field(default=False)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Alert(BaseModel):
    """Model for monitoring alerts."""
    
    id: str = Field(..., description="Unique alert ID")
    type: AlertType = Field(..., description="Type of alert")
    severity: ErrorSeverity = Field(..., description="Alert severity")
    title: str = Field(..., description="Alert title")
    message: str = Field(..., description="Alert message")
    url: str = Field(..., description="URL related to the alert")
    triggered_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = Field(None)
    notification_sent: bool = Field(default=False)
    channels_notified: List[NotificationChannel] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MonitoringMetrics(BaseModel):
    """Monitoring metrics for an application."""
    
    url: str = Field(..., description="URL being monitored")
    uptime_percentage: float = Field(..., description="Uptime percentage")
    average_response_time: float = Field(..., description="Average response time in ms")
    error_rate: float = Field(..., description="Error rate percentage")
    total_requests: int = Field(..., description="Total number of requests")
    error_count: int = Field(..., description="Total number of errors")
    last_24h_errors: List[ErrorEvent] = Field(default_factory=list)
    performance_score: Optional[float] = Field(None, description="Performance score (0-100)")
    collected_at: datetime = Field(default_factory=datetime.utcnow)


class NotificationConfig(BaseModel):
    """Configuration for notifications."""
    
    channel: NotificationChannel = Field(..., description="Notification channel")
    enabled: bool = Field(default=True)
    config: Dict[str, Any] = Field(default_factory=dict, description="Channel-specific configuration")
    severity_threshold: ErrorSeverity = Field(default=ErrorSeverity.MEDIUM)
    throttle_minutes: int = Field(default=5, description="Minutes to wait between similar notifications")


class MonitoringSetup(BaseModel):
    """Configuration for setting up monitoring for an application."""
    
    url: str = Field(..., description="URL to monitor")
    project_id: str = Field(..., description="Project ID")
    check_interval: int = Field(default=300, description="Check interval in seconds")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    error_tracking_enabled: bool = Field(default=True)
    uptime_monitoring_enabled: bool = Field(default=True)
    performance_monitoring_enabled: bool = Field(default=False)
    notification_configs: List[NotificationConfig] = Field(default_factory=list)
    alert_thresholds: Dict[str, Any] = Field(default_factory=dict)
    custom_headers: Dict[str, str] = Field(default_factory=dict)


class HealthCheckTool(ToolInterface):
    """Abstract interface for health check and uptime monitoring."""
    
    @abstractmethod
    async def check_health(self, url: str, timeout: int = 30) -> HealthStatus:
        """Check the health status of a URL."""
        pass
    
    @abstractmethod
    async def setup_uptime_monitoring(self, config: MonitoringSetup) -> Dict[str, Any]:
        """Set up continuous uptime monitoring for a URL."""
        pass
    
    @abstractmethod
    async def get_uptime_metrics(self, url: str, time_period: timedelta = timedelta(days=1)) -> MonitoringMetrics:
        """Get uptime metrics for a URL over a time period."""
        pass
    
    @abstractmethod
    async def stop_monitoring(self, url: str) -> bool:
        """Stop monitoring a URL."""
        pass
    
    async def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a health check command."""
        if command == "check":
            url = parameters.get("url")
            timeout = parameters.get("timeout", 30)
            if not url:
                raise ValueError("URL is required for health check")
            
            result = await self.check_health(url, timeout)
            return {"health_status": result.dict()}
        
        elif command == "setup_monitoring":
            config = MonitoringSetup(**parameters.get("config", {}))
            result = await self.setup_uptime_monitoring(config)
            return {"monitoring_setup": result}
        
        elif command == "get_metrics":
            url = parameters.get("url")
            time_period_hours = parameters.get("time_period_hours", 24)
            time_period = timedelta(hours=time_period_hours)
            
            if not url:
                raise ValueError("URL is required for metrics")
            
            result = await self.get_uptime_metrics(url, time_period)
            return {"metrics": result.dict()}
        
        elif command == "stop":
            url = parameters.get("url")
            if not url:
                raise ValueError("URL is required to stop monitoring")
            
            result = await self.stop_monitoring(url)
            return {"stopped": result}
        
        else:
            raise ValueError(f"Unknown health check command: {command}")


class ErrorTrackingTool(ToolInterface):
    """Abstract interface for error tracking and analysis."""
    
    @abstractmethod
    async def setup_error_tracking(self, url: str, project_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Set up error tracking for an application."""
        pass
    
    @abstractmethod
    async def get_errors(self, url: str, time_period: timedelta = timedelta(hours=24)) -> List[ErrorEvent]:
        """Get errors for a URL over a time period."""
        pass
    
    @abstractmethod
    async def analyze_error_patterns(self, errors: List[ErrorEvent]) -> Dict[str, Any]:
        """Analyze error patterns and trends."""
        pass
    
    @abstractmethod
    async def categorize_error(self, error: ErrorEvent) -> ErrorSeverity:
        """Categorize an error by severity."""
        pass
    
    @abstractmethod
    async def resolve_error(self, error_id: str) -> bool:
        """Mark an error as resolved."""
        pass
    
    async def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an error tracking command."""
        if command == "setup":
            url = parameters.get("url")
            project_id = parameters.get("project_id")
            config = parameters.get("config", {})
            
            if not url or not project_id:
                raise ValueError("URL and project_id are required for error tracking setup")
            
            result = await self.setup_error_tracking(url, project_id, config)
            return {"error_tracking_setup": result}
        
        elif command == "get_errors":
            url = parameters.get("url")
            time_period_hours = parameters.get("time_period_hours", 24)
            time_period = timedelta(hours=time_period_hours)
            
            if not url:
                raise ValueError("URL is required to get errors")
            
            errors = await self.get_errors(url, time_period)
            return {"errors": [error.dict() for error in errors]}
        
        elif command == "analyze":
            errors_data = parameters.get("errors", [])
            errors = [ErrorEvent(**error) for error in errors_data]
            
            analysis = await self.analyze_error_patterns(errors)
            return {"analysis": analysis}
        
        elif command == "categorize":
            error_data = parameters.get("error", {})
            error = ErrorEvent(**error_data)
            
            severity = await self.categorize_error(error)
            return {"severity": severity.value}
        
        elif command == "resolve":
            error_id = parameters.get("error_id")
            if not error_id:
                raise ValueError("Error ID is required to resolve error")
            
            result = await self.resolve_error(error_id)
            return {"resolved": result}
        
        else:
            raise ValueError(f"Unknown error tracking command: {command}")


class NotificationTool(ToolInterface):
    """Abstract interface for sending notifications and alerts."""
    
    @abstractmethod
    async def send_notification(self, channel: NotificationChannel, message: str, config: Dict[str, Any]) -> bool:
        """Send a notification through the specified channel."""
        pass
    
    @abstractmethod
    async def send_alert(self, alert: Alert, channels: List[NotificationChannel]) -> Dict[str, bool]:
        """Send an alert through multiple channels."""
        pass
    
    @abstractmethod
    async def configure_channel(self, channel: NotificationChannel, config: Dict[str, Any]) -> bool:
        """Configure a notification channel."""
        pass
    
    @abstractmethod
    async def test_channel(self, channel: NotificationChannel, config: Dict[str, Any]) -> bool:
        """Test a notification channel configuration."""
        pass
    
    async def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a notification command."""
        if command == "send":
            channel_str = parameters.get("channel")
            message = parameters.get("message")
            config = parameters.get("config", {})
            
            if not channel_str or not message:
                raise ValueError("Channel and message are required for notification")
            
            channel = NotificationChannel(channel_str)
            result = await self.send_notification(channel, message, config)
            return {"sent": result}
        
        elif command == "send_alert":
            alert_data = parameters.get("alert", {})
            channels_data = parameters.get("channels", [])
            
            alert = Alert(**alert_data)
            channels = [NotificationChannel(ch) for ch in channels_data]
            
            results = await self.send_alert(alert, channels)
            return {"results": results}
        
        elif command == "configure":
            channel_str = parameters.get("channel")
            config = parameters.get("config", {})
            
            if not channel_str:
                raise ValueError("Channel is required for configuration")
            
            channel = NotificationChannel(channel_str)
            result = await self.configure_channel(channel, config)
            return {"configured": result}
        
        elif command == "test":
            channel_str = parameters.get("channel")
            config = parameters.get("config", {})
            
            if not channel_str:
                raise ValueError("Channel is required for testing")
            
            channel = NotificationChannel(channel_str)
            result = await self.test_channel(channel, config)
            return {"test_passed": result}
        
        else:
            raise ValueError(f"Unknown notification command: {command}")