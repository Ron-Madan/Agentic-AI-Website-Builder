"""Monitoring integration module for post-deployment monitoring."""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from ..agents.monitor import MonitorAgent
from ..tools.monitoring_interfaces import MonitoringSetup, Alert, AlertType, ErrorSeverity
from ..models.project import MonitoringConfig


logger = logging.getLogger(__name__)


async def setup_monitoring(
    project_id: str,
    deployment_url: str,
    monitor_agent: Optional[MonitorAgent] = None,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Set up comprehensive monitoring for a deployed application.
    
    Args:
        project_id: Unique identifier for the project
        deployment_url: URL of the deployed application
        monitor_agent: MonitorAgent instance to use for monitoring
        config: Optional monitoring configuration overrides
    
    Returns:
        Dictionary containing monitoring setup results
    
    Requirements: 2.1, 2.2
    """
    logger.info(f"Setting up monitoring for project {project_id} at {deployment_url}")
    
    if not monitor_agent:
        logger.warning(f"No monitor agent available for project {project_id}")
        return {
            "project_id": project_id,
            "url": deployment_url,
            "monitoring_active": False,
            "error": "Monitor agent not available",
            "setup_time": datetime.utcnow().isoformat()
        }
    
    try:
        # Create monitoring configuration
        monitoring_config = MonitoringSetup(
            url=deployment_url,
            project_id=project_id,
            check_interval=config.get("check_interval", 300) if config else 300,  # 5 minutes default
            timeout=config.get("timeout", 30) if config else 30,
            error_tracking_enabled=config.get("error_tracking_enabled", True) if config else True,
            uptime_monitoring_enabled=config.get("uptime_monitoring_enabled", True) if config else True,
            performance_monitoring_enabled=config.get("performance_monitoring_enabled", False) if config else False,
            notification_configs=[],
            alert_thresholds={
                "error_rate_threshold": config.get("error_rate_threshold", 5.0) if config else 5.0,
                "response_time_threshold": config.get("response_time_threshold", 5000) if config else 5000,
                "uptime_threshold": config.get("uptime_threshold", 95.0) if config else 95.0
            }
        )
        
        # Set up monitoring using the monitor agent
        setup_result = await monitor_agent._setup_monitoring(
            {"deployment_info": {"url": deployment_url}},
            type("Task", (), {
                "id": f"{project_id}_monitoring_setup",
                "metadata": {"action": "setup"}
            })()
        )
        
        logger.info(f"Monitoring setup completed for project {project_id}")
        
        return {
            "project_id": project_id,
            "url": deployment_url,
            "monitoring_active": setup_result.get("monitoring_active", True),
            "health_monitoring": setup_result.get("health_monitoring", {}),
            "error_tracking": setup_result.get("error_tracking", {}),
            "notifications": setup_result.get("notifications", {}),
            "check_interval": monitoring_config.check_interval,
            "alert_thresholds": monitoring_config.alert_thresholds,
            "setup_time": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to set up monitoring for project {project_id}: {str(e)}")
        return {
            "project_id": project_id,
            "url": deployment_url,
            "monitoring_active": False,
            "error": str(e),
            "setup_time": datetime.utcnow().isoformat()
        }


async def get_monitoring_status(
    project_id: str,
    monitor_agent: Optional[MonitorAgent] = None
) -> Dict[str, Any]:
    """
    Get current monitoring status for a project.
    
    Args:
        project_id: Unique identifier for the project
        monitor_agent: MonitorAgent instance to query
    
    Returns:
        Dictionary containing current monitoring status
    
    Requirements: 2.5
    """
    logger.debug(f"Getting monitoring status for project {project_id}")
    
    if not monitor_agent:
        return {
            "project_id": project_id,
            "monitoring_active": False,
            "error": "Monitor agent not available",
            "status_time": datetime.utcnow().isoformat()
        }
    
    try:
        # Check if monitoring is active for this project
        monitoring_status = monitor_agent.get_monitoring_status()
        
        if project_id not in monitoring_status.get("monitored_projects", []):
            return {
                "project_id": project_id,
                "monitoring_active": False,
                "message": "No active monitoring for this project",
                "status_time": datetime.utcnow().isoformat()
            }
        
        # Get detailed monitoring report
        monitoring_report = await monitor_agent.get_project_monitoring_report(project_id)
        
        return {
            "project_id": project_id,
            "monitoring_active": True,
            "url": monitoring_report.get("url"),
            "monitoring_started": monitoring_report.get("monitoring_started"),
            "health_metrics": monitoring_report.get("health_metrics", {}),
            "error_analysis": monitoring_report.get("error_analysis", {}),
            "notification_stats": monitoring_report.get("notification_stats", {}),
            "status_time": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get monitoring status for project {project_id}: {str(e)}")
        return {
            "project_id": project_id,
            "monitoring_active": False,
            "error": str(e),
            "status_time": datetime.utcnow().isoformat()
        }


async def get_monitoring_metrics(
    project_id: str,
    monitor_agent: Optional[MonitorAgent] = None,
    time_period_hours: int = 24
) -> Dict[str, Any]:
    """
    Get monitoring metrics for a project over a specified time period.
    
    Args:
        project_id: Unique identifier for the project
        monitor_agent: MonitorAgent instance to query
        time_period_hours: Number of hours to look back for metrics
    
    Returns:
        Dictionary containing monitoring metrics
    
    Requirements: 2.6
    """
    logger.debug(f"Getting monitoring metrics for project {project_id} over {time_period_hours} hours")
    
    if not monitor_agent:
        return {
            "project_id": project_id,
            "error": "Monitor agent not available",
            "metrics_time": datetime.utcnow().isoformat()
        }
    
    try:
        # Get monitoring report which includes metrics
        monitoring_report = await monitor_agent.get_project_monitoring_report(project_id)
        
        if "error" in monitoring_report:
            return {
                "project_id": project_id,
                "error": monitoring_report["error"],
                "metrics_time": datetime.utcnow().isoformat()
            }
        
        # Extract metrics from the report
        health_metrics = monitoring_report.get("health_metrics", {})
        error_analysis = monitoring_report.get("error_analysis", {})
        
        # Calculate additional metrics
        uptime_percentage = health_metrics.get("uptime_percentage", 0.0)
        average_response_time = health_metrics.get("average_response_time", 0.0)
        error_rate = health_metrics.get("error_rate", 0.0)
        total_requests = health_metrics.get("total_requests", 0)
        error_count = health_metrics.get("error_count", 0)
        
        # Get recent errors
        recent_errors = health_metrics.get("last_24h_errors", [])
        
        # Categorize errors by severity
        error_breakdown = {
            "critical": len([e for e in recent_errors if e.get("severity") == "critical"]),
            "high": len([e for e in recent_errors if e.get("severity") == "high"]),
            "medium": len([e for e in recent_errors if e.get("severity") == "medium"]),
            "low": len([e for e in recent_errors if e.get("severity") == "low"])
        }
        
        return {
            "project_id": project_id,
            "url": monitoring_report.get("url"),
            "time_period_hours": time_period_hours,
            "uptime": {
                "percentage": uptime_percentage,
                "status": "healthy" if uptime_percentage >= 95.0 else "degraded" if uptime_percentage >= 90.0 else "unhealthy"
            },
            "performance": {
                "average_response_time_ms": average_response_time,
                "total_requests": total_requests,
                "status": "good" if average_response_time < 1000 else "fair" if average_response_time < 3000 else "poor"
            },
            "errors": {
                "total_count": error_count,
                "error_rate_percentage": error_rate,
                "breakdown_by_severity": error_breakdown,
                "recent_errors": recent_errors[:10],  # Last 10 errors
                "status": "healthy" if error_rate < 1.0 else "warning" if error_rate < 5.0 else "critical"
            },
            "trends": error_analysis.get("trends", {}),
            "alerts_triggered": error_analysis.get("alerts_triggered", 0),
            "last_check": health_metrics.get("collected_at"),
            "metrics_time": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get monitoring metrics for project {project_id}: {str(e)}")
        return {
            "project_id": project_id,
            "error": str(e),
            "metrics_time": datetime.utcnow().isoformat()
        }


async def stop_monitoring(
    project_id: str,
    monitor_agent: Optional[MonitorAgent] = None
) -> Dict[str, Any]:
    """
    Stop monitoring for a specific project.
    
    Args:
        project_id: Unique identifier for the project
        monitor_agent: MonitorAgent instance to use
    
    Returns:
        Dictionary containing stop operation results
    """
    logger.info(f"Stopping monitoring for project {project_id}")
    
    if not monitor_agent:
        return {
            "project_id": project_id,
            "stopped": False,
            "error": "Monitor agent not available",
            "stop_time": datetime.utcnow().isoformat()
        }
    
    try:
        # Stop monitoring using the monitor agent
        stopped = await monitor_agent.stop_monitoring(project_id)
        
        return {
            "project_id": project_id,
            "stopped": stopped,
            "message": "Monitoring stopped successfully" if stopped else "No active monitoring found",
            "stop_time": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to stop monitoring for project {project_id}: {str(e)}")
        return {
            "project_id": project_id,
            "stopped": False,
            "error": str(e),
            "stop_time": datetime.utcnow().isoformat()
        }


def create_monitoring_config(
    error_tracking_enabled: bool = True,
    uptime_monitoring_enabled: bool = True,
    performance_monitoring_enabled: bool = False,
    notification_channels: Optional[List[str]] = None,
    alert_thresholds: Optional[Dict[str, Any]] = None
) -> MonitoringConfig:
    """
    Create a monitoring configuration object.
    
    Args:
        error_tracking_enabled: Whether to enable error tracking
        uptime_monitoring_enabled: Whether to enable uptime monitoring
        performance_monitoring_enabled: Whether to enable performance monitoring
        notification_channels: List of notification channels to use
        alert_thresholds: Custom alert thresholds
    
    Returns:
        MonitoringConfig object
    """
    return MonitoringConfig(
        error_tracking_enabled=error_tracking_enabled,
        uptime_monitoring_enabled=uptime_monitoring_enabled,
        performance_monitoring_enabled=performance_monitoring_enabled,
        notification_channels=notification_channels or [],
        alert_thresholds=alert_thresholds or {
            "error_rate_threshold": 5.0,
            "response_time_threshold": 5000,
            "uptime_threshold": 95.0
        }
    )


async def handle_monitoring_alert(
    project_id: str,
    alert: Alert,
    monitor_agent: Optional[MonitorAgent] = None
) -> Dict[str, Any]:
    """
    Handle a monitoring alert for a project.
    
    Args:
        project_id: Unique identifier for the project
        alert: Alert object containing alert details
        monitor_agent: MonitorAgent instance to use
    
    Returns:
        Dictionary containing alert handling results
    """
    logger.warning(f"Handling monitoring alert for project {project_id}: {alert.title}")
    
    if not monitor_agent:
        return {
            "project_id": project_id,
            "alert_id": alert.id,
            "handled": False,
            "error": "Monitor agent not available",
            "handle_time": datetime.utcnow().isoformat()
        }
    
    try:
        # Process the alert through the monitor agent's alert manager
        if monitor_agent.alert_manager:
            await monitor_agent.alert_manager.process_alert(alert)
            
            return {
                "project_id": project_id,
                "alert_id": alert.id,
                "alert_type": alert.type.value,
                "severity": alert.severity.value,
                "handled": True,
                "message": "Alert processed successfully",
                "handle_time": datetime.utcnow().isoformat()
            }
        else:
            logger.warning(f"No alert manager available for project {project_id}")
            return {
                "project_id": project_id,
                "alert_id": alert.id,
                "handled": False,
                "error": "Alert manager not available",
                "handle_time": datetime.utcnow().isoformat()
            }
        
    except Exception as e:
        logger.error(f"Failed to handle monitoring alert for project {project_id}: {str(e)}")
        return {
            "project_id": project_id,
            "alert_id": alert.id,
            "handled": False,
            "error": str(e),
            "handle_time": datetime.utcnow().isoformat()
        }