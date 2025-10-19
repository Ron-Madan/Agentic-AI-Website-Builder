"""Monitor Agent implementation for continuous monitoring."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from ..agents.base import MonitorAgentBase
from ..core.interfaces import Task, EventType, TaskType
from ..models.project import ProjectState
from ..tools.monitoring_interfaces import (
    HealthCheckTool, ErrorTrackingTool, NotificationTool,
    MonitoringSetup, Alert, AlertType, ErrorSeverity, NotificationChannel
)
from ..tools.alert_manager import AlertManager


logger = logging.getLogger(__name__)


class MonitorAgent(MonitorAgentBase):
    """Agent responsible for continuous monitoring of deployed applications."""
    
    def __init__(self, state_manager: 'StateManager'):
        super().__init__(state_manager)
        self.health_monitor: Optional[HealthCheckTool] = None
        self.error_tracker: Optional[ErrorTrackingTool] = None
        self.notification_system: Optional[NotificationTool] = None
        self.alert_manager: Optional[AlertManager] = None
        self._monitoring_configs: Dict[str, MonitoringSetup] = {}
        self._active_monitors: Dict[str, Dict[str, Any]] = {}
        
        # Register event handlers
        self.register_event_handler(EventType.TESTS_COMPLETED, self._handle_tests_completed)
        self.register_event_handler(EventType.ERROR_DETECTED, self._handle_error_detected)
    
    def set_tools(self, 
                  health_monitor: HealthCheckTool,
                  error_tracker: ErrorTrackingTool,
                  notification_system: NotificationTool) -> None:
        """Set the monitoring tools for the agent."""
        self.health_monitor = health_monitor
        self.error_tracker = error_tracker
        self.notification_system = notification_system
        self.alert_manager = AlertManager(notification_system)
        self.logger.info("Monitoring tools configured successfully")
    
    async def start(self) -> None:
        """Start the monitor agent and its tools."""
        await super().start()
        
        if self.health_monitor:
            await self.health_monitor.start()
        if self.error_tracker:
            await self.error_tracker.start()
        if self.notification_system:
            await self.notification_system.start()
        
        self.logger.info("Monitor agent started with all tools")
    
    async def stop(self) -> None:
        """Stop the monitor agent and cleanup resources."""
        # Stop all active monitoring
        for project_id in list(self._active_monitors.keys()):
            await self.stop_monitoring(project_id)
        
        # Stop tools
        if self.alert_manager:
            await self.alert_manager.cleanup()
        if self.health_monitor:
            await self.health_monitor.stop()
        if self.error_tracker:
            await self.error_tracker.stop()
        if self.notification_system:
            await self.notification_system.stop()
        
        await super().stop()
        self.logger.info("Monitor agent stopped")
    
    async def _execute_task_impl(self, task: Task) -> Dict[str, Any]:
        """Execute monitoring tasks."""
        self.logger.info(f"Executing monitoring task: {task.description}")
        
        if task.type != TaskType.MONITORING:
            raise ValueError(f"Invalid task type for MonitorAgent: {task.type}")
        
        # Get project state
        project_id = task.id.split("_")[0]
        project_state_data = await self.state_manager.get_project_state(project_id)
        if not project_state_data:
            raise ValueError(f"Project state not found for project {project_id}")
        
        # Determine monitoring action from task metadata
        action = task.metadata.get("action", "setup") if task.metadata else "setup"
        
        if action == "setup":
            return await self._setup_monitoring(project_state_data, task)
        elif action == "check_health":
            return await self._check_application_health(project_state_data, task)
        elif action == "analyze_errors":
            return await self._analyze_errors(project_state_data, task)
        elif action == "send_alert":
            return await self._send_alert(project_state_data, task)
        else:
            raise ValueError(f"Unsupported monitoring action: {action}")
    
    async def _setup_monitoring(self, project_state_data: Dict[str, Any], task: Task) -> Dict[str, Any]:
        """Set up comprehensive monitoring for a deployed application."""
        if not all([self.health_monitor, self.error_tracker, self.notification_system]):
            raise ValueError("All monitoring tools must be configured")
        
        project_id = task.id.split("_")[0]
        deployment_info = project_state_data.get("deployment_info")
        
        if not deployment_info:
            raise ValueError("No deployment information found for monitoring setup")
        
        url = deployment_info.get("url")
        if not url:
            raise ValueError("Deployment URL not found")
        
        self.logger.info(f"Setting up monitoring for {url}")
        
        # Create monitoring configuration
        monitoring_config = MonitoringSetup(
            url=url,
            project_id=project_id,
            check_interval=300,  # 5 minutes
            timeout=30,
            error_tracking_enabled=True,
            uptime_monitoring_enabled=True,
            performance_monitoring_enabled=False,
            notification_configs=[],
            alert_thresholds={
                "error_rate_threshold": 5.0,  # 5% error rate
                "response_time_threshold": 5000,  # 5 seconds
                "uptime_threshold": 95.0  # 95% uptime
            }
        )
        
        # Store configuration
        self._monitoring_configs[project_id] = monitoring_config
        
        # Set up health monitoring
        health_setup = await self.health_monitor.setup_uptime_monitoring(monitoring_config)
        
        # Set up error tracking
        error_setup = await self.error_tracker.setup_error_tracking(url, project_id, {
            "check_interval": 300,
            "severity_threshold": "medium"
        })
        
        # Configure default notification channels (if configured)
        notification_setup = await self._setup_default_notifications(project_id)
        
        # Store active monitoring info
        self._active_monitors[project_id] = {
            "url": url,
            "health_monitoring": health_setup,
            "error_tracking": error_setup,
            "notifications": notification_setup,
            "started_at": datetime.utcnow().isoformat()
        }
        
        self.logger.info(f"Monitoring setup completed for project {project_id}")
        
        return {
            "project_id": project_id,
            "url": url,
            "monitoring_active": True,
            "health_monitoring": health_setup,
            "error_tracking": error_setup,
            "notifications": notification_setup
        }
    
    async def _check_application_health(self, project_state_data: Dict[str, Any], task: Task) -> Dict[str, Any]:
        """Check the health status of a deployed application."""
        if not self.health_monitor:
            raise ValueError("Health monitor not configured")
        
        project_id = task.id.split("_")[0]
        deployment_info = project_state_data.get("deployment_info")
        
        if not deployment_info:
            raise ValueError("No deployment information found")
        
        url = deployment_info.get("url")
        if not url:
            raise ValueError("Deployment URL not found")
        
        self.logger.info(f"Checking health for {url}")
        
        # Perform health check
        health_status = await self.health_monitor.check_health(url)
        
        # Get metrics for the last 24 hours
        metrics = await self.health_monitor.get_uptime_metrics(url, timedelta(hours=24))
        
        # Check if health status requires alerting
        if health_status.status == "down":
            await self._create_health_alert(project_id, url, health_status, ErrorSeverity.CRITICAL)
        elif health_status.status == "degraded":
            await self._create_health_alert(project_id, url, health_status, ErrorSeverity.HIGH)
        
        return {
            "project_id": project_id,
            "url": url,
            "health_status": health_status.dict(),
            "metrics": metrics.dict(),
            "check_time": datetime.utcnow().isoformat()
        }
    
    async def _analyze_errors(self, project_state_data: Dict[str, Any], task: Task) -> Dict[str, Any]:
        """Analyze errors for a deployed application."""
        if not self.error_tracker:
            raise ValueError("Error tracker not configured")
        
        project_id = task.id.split("_")[0]
        deployment_info = project_state_data.get("deployment_info")
        
        if not deployment_info:
            raise ValueError("No deployment information found")
        
        url = deployment_info.get("url")
        if not url:
            raise ValueError("Deployment URL not found")
        
        self.logger.info(f"Analyzing errors for {url}")
        
        # Get errors from the last 24 hours
        time_period = timedelta(hours=24)
        errors = await self.error_tracker.get_errors(url, time_period)
        
        # Analyze error patterns
        analysis = await self.error_tracker.analyze_error_patterns(errors)
        
        # Check if error analysis requires alerting
        critical_errors = [e for e in errors if e.severity == ErrorSeverity.CRITICAL]
        if critical_errors:
            await self._create_error_alert(project_id, url, critical_errors)
        
        # Check error rate threshold
        config = self._monitoring_configs.get(project_id)
        if config and analysis.get("trends", {}).get("last_hour_count", 0) > 10:
            await self._create_error_rate_alert(project_id, url, analysis)
        
        return {
            "project_id": project_id,
            "url": url,
            "error_count": len(errors),
            "critical_errors": len(critical_errors),
            "analysis": analysis,
            "analyzed_at": datetime.utcnow().isoformat()
        }
    
    async def _send_alert(self, project_state_data: Dict[str, Any], task: Task) -> Dict[str, Any]:
        """Send an alert through configured notification channels."""
        if not self.notification_system:
            raise ValueError("Notification system not configured")
        
        # Extract alert information from task metadata
        alert_data = task.metadata.get("alert", {}) if task.metadata else {}
        if not alert_data:
            raise ValueError("No alert data provided in task metadata")
        
        # Create alert object
        alert = Alert(**alert_data)
        
        # Get configured notification channels
        channels = task.metadata.get("channels", [NotificationChannel.EMAIL.value])
        notification_channels = [NotificationChannel(ch) for ch in channels]
        
        # Send alert
        results = await self.notification_system.send_alert(alert, notification_channels)
        
        self.logger.info(f"Alert sent: {alert.title} - Results: {results}")
        
        return {
            "alert_id": alert.id,
            "alert_sent": any(results.values()),
            "channel_results": results,
            "sent_at": datetime.utcnow().isoformat()
        }
    
    async def _setup_default_notifications(self, project_id: str) -> Dict[str, Any]:
        """Set up default notification channels if configured."""
        # This is a placeholder for setting up default notifications
        # In a real implementation, you would configure channels based on project settings
        
        return {
            "email_configured": False,
            "slack_configured": False,
            "webhook_configured": False,
            "default_channels": []
        }
    
    async def _create_health_alert(self, project_id: str, url: str, health_status, severity: ErrorSeverity) -> None:
        """Create and send a health-related alert."""
        alert = Alert(
            id=f"{project_id}_health_{datetime.utcnow().isoformat()}",
            type=AlertType.UPTIME,
            severity=severity,
            title=f"Health Check Alert: {health_status.status.upper()}",
            message=f"Application at {url} is {health_status.status}. {health_status.error_message or ''}",
            url=url,
            metadata={
                "response_time": health_status.response_time,
                "status_code": health_status.status_code,
                "project_id": project_id
            }
        )
        
        # Process alert through alert manager
        if self.alert_manager:
            await self.alert_manager.process_alert(alert)
    
    async def _create_error_alert(self, project_id: str, url: str, critical_errors: List) -> None:
        """Create and send an error-related alert."""
        alert = Alert(
            id=f"{project_id}_errors_{datetime.utcnow().isoformat()}",
            type=AlertType.ERROR,
            severity=ErrorSeverity.CRITICAL,
            title=f"Critical Errors Detected",
            message=f"Found {len(critical_errors)} critical errors on {url}",
            url=url,
            metadata={
                "error_count": len(critical_errors),
                "project_id": project_id,
                "errors": [{"type": e.error_type, "message": e.message} for e in critical_errors[:5]]
            }
        )
        
        # Process alert through alert manager
        if self.alert_manager:
            await self.alert_manager.process_alert(alert)
    
    async def _create_error_rate_alert(self, project_id: str, url: str, analysis: Dict[str, Any]) -> None:
        """Create and send an error rate alert."""
        error_count = analysis.get("trends", {}).get("last_hour_count", 0)
        
        alert = Alert(
            id=f"{project_id}_error_rate_{datetime.utcnow().isoformat()}",
            type=AlertType.ERROR,
            severity=ErrorSeverity.HIGH,
            title=f"High Error Rate Detected",
            message=f"High error rate detected: {error_count} errors in the last hour on {url}",
            url=url,
            metadata={
                "error_count_last_hour": error_count,
                "project_id": project_id,
                "analysis": analysis
            }
        )
        
        # Process alert through alert manager
        if self.alert_manager:
            await self.alert_manager.process_alert(alert)
    
    async def stop_monitoring(self, project_id: str) -> bool:
        """Stop monitoring for a specific project."""
        if project_id not in self._active_monitors:
            return False
        
        monitor_info = self._active_monitors[project_id]
        url = monitor_info.get("url")
        
        # Stop health monitoring
        if self.health_monitor and url:
            await self.health_monitor.stop_monitoring(url)
        
        # Remove from active monitors
        del self._active_monitors[project_id]
        
        # Remove configuration
        if project_id in self._monitoring_configs:
            del self._monitoring_configs[project_id]
        
        self.logger.info(f"Stopped monitoring for project {project_id}")
        return True
    
    async def _handle_tests_completed(self, event) -> None:
        """Handle test completion events to set up monitoring."""
        project_id = event.payload.get("project_id")
        test_type = event.payload.get("test_type")
        success = event.payload.get("success", False)
        
        if not project_id or test_type != "ui" or not success:
            return
        
        self.logger.info(f"UI tests completed successfully for {project_id} - setting up monitoring")
        
        # Create monitoring setup task
        monitoring_task = Task(
            id=f"{project_id}_monitoring_setup_{datetime.utcnow().isoformat()}",
            type=TaskType.MONITORING,
            description="Set up monitoring for deployed application",
            dependencies=[],
            estimated_duration=300,  # 5 minutes
            status="pending",
            agent_assigned=self.agent_id,
            metadata={"action": "setup", "triggered_by": "tests_completed"}
        )
        
        try:
            result = await self.execute_task(monitoring_task)
            
            # Publish monitoring setup completion event
            await self.publish_event(EventType.TASK_COMPLETED, {
                "project_id": project_id,
                "task_type": "monitoring_setup",
                "success": True,
                "monitoring_active": result.get("monitoring_active", False)
            })
            
        except Exception as e:
            self.logger.error(f"Failed to set up monitoring for {project_id}: {str(e)}")
            await self.publish_event(EventType.ERROR_DETECTED, {
                "project_id": project_id,
                "error": str(e),
                "context": "monitoring_setup"
            })
    
    async def _handle_error_detected(self, event) -> None:
        """Handle error detection events from other agents."""
        project_id = event.payload.get("project_id")
        error = event.payload.get("error")
        context = event.payload.get("context", "unknown")
        
        if not project_id:
            return
        
        self.logger.info(f"Error detected for {project_id} in context {context}: {error}")
        
        # If monitoring is active for this project, create an alert
        if project_id in self._active_monitors:
            monitor_info = self._active_monitors[project_id]
            url = monitor_info.get("url", "unknown")
            
            alert = Alert(
                id=f"{project_id}_system_error_{datetime.utcnow().isoformat()}",
                type=AlertType.ERROR,
                severity=ErrorSeverity.HIGH,
                title=f"System Error in {context}",
                message=f"Error detected in {context}: {error}",
                url=url,
                metadata={
                    "project_id": project_id,
                    "context": context,
                    "error": error
                }
            )
            
            # Process alert through alert manager
            if self.alert_manager:
                await self.alert_manager.process_alert(alert)
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status for all projects."""
        return {
            "active_monitors": len(self._active_monitors),
            "monitored_projects": list(self._active_monitors.keys()),
            "monitoring_configs": len(self._monitoring_configs),
            "tools_configured": {
                "health_monitor": self.health_monitor is not None,
                "error_tracker": self.error_tracker is not None,
                "notification_system": self.notification_system is not None
            }
        }
    
    async def get_project_monitoring_report(self, project_id: str) -> Dict[str, Any]:
        """Generate a comprehensive monitoring report for a project."""
        if project_id not in self._active_monitors:
            return {"error": "No active monitoring for this project"}
        
        monitor_info = self._active_monitors[project_id]
        url = monitor_info.get("url")
        
        report = {
            "project_id": project_id,
            "url": url,
            "monitoring_started": monitor_info.get("started_at"),
            "report_generated": datetime.utcnow().isoformat()
        }
        
        # Get health metrics
        if self.health_monitor and url:
            try:
                health_metrics = await self.health_monitor.get_uptime_metrics(url, timedelta(hours=24))
                report["health_metrics"] = health_metrics.dict()
            except Exception as e:
                report["health_metrics_error"] = str(e)
        
        # Get error analysis
        if self.error_tracker and url:
            try:
                errors = await self.error_tracker.get_errors(url, timedelta(hours=24))
                error_analysis = await self.error_tracker.analyze_error_patterns(errors)
                report["error_analysis"] = error_analysis
            except Exception as e:
                report["error_analysis_error"] = str(e)
        
        # Get notification statistics
        if self.notification_system:
            try:
                notification_stats = self.notification_system.get_notification_statistics()
                report["notification_stats"] = notification_stats
            except Exception as e:
                report["notification_stats_error"] = str(e)
        
        return report