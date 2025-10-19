"""Factory for creating Monitor Agent with configured tools."""

import logging
from typing import Optional

from ..agents.monitor import MonitorAgent
from ..tools.health_monitoring import HealthMonitor
from ..tools.error_tracking import ErrorTracker
from ..tools.notification_system import NotificationSystem
from ..tools.alert_manager import AlertManager
from ..core.config import get_settings


logger = logging.getLogger(__name__)


class MonitorAgentFactory:
    """Factory for creating Monitor Agent instances with configured tools."""
    
    @staticmethod
    def create_monitor_agent(state_manager: 'StateManager') -> MonitorAgent:
        """Create a Monitor Agent with all necessary tools configured."""
        settings = get_settings()
        
        # Create the monitor agent
        monitor_agent = MonitorAgent(state_manager)
        
        # Create and configure monitoring tools
        health_monitor = HealthMonitor()
        error_tracker = ErrorTracker()
        notification_system = NotificationSystem()
        
        # Configure notification system with default channels if available
        MonitorAgentFactory._configure_notification_system(notification_system, settings)
        
        # Set tools on the agent
        monitor_agent.set_tools(
            health_monitor=health_monitor,
            error_tracker=error_tracker,
            notification_system=notification_system
        )
        
        logger.info("Monitor agent created with all tools configured")
        return monitor_agent
    
    @staticmethod
    def _configure_notification_system(notification_system: NotificationSystem, settings) -> None:
        """Configure notification system with available settings."""
        try:
            # Configure email if settings are available
            email_config = getattr(settings, 'EMAIL_CONFIG', None)
            if email_config and isinstance(email_config, dict):
                from ..tools.monitoring_interfaces import NotificationChannel
                notification_system.configure_channel(NotificationChannel.EMAIL, email_config)
                logger.info("Email notifications configured")
            
            # Configure Slack if settings are available
            slack_config = getattr(settings, 'SLACK_CONFIG', None)
            if slack_config and isinstance(slack_config, dict):
                from ..tools.monitoring_interfaces import NotificationChannel
                notification_system.configure_channel(NotificationChannel.SLACK, slack_config)
                logger.info("Slack notifications configured")
            
            # Configure webhook if settings are available
            webhook_config = getattr(settings, 'WEBHOOK_CONFIG', None)
            if webhook_config and isinstance(webhook_config, dict):
                from ..tools.monitoring_interfaces import NotificationChannel
                notification_system.configure_channel(NotificationChannel.WEBHOOK, webhook_config)
                logger.info("Webhook notifications configured")
                
        except Exception as e:
            logger.warning(f"Failed to configure some notification channels: {str(e)}")
    
    @staticmethod
    def create_health_monitor() -> HealthMonitor:
        """Create a standalone health monitor."""
        return HealthMonitor()
    
    @staticmethod
    def create_error_tracker() -> ErrorTracker:
        """Create a standalone error tracker."""
        return ErrorTracker()
    
    @staticmethod
    def create_notification_system() -> NotificationSystem:
        """Create a standalone notification system."""
        notification_system = NotificationSystem()
        settings = get_settings()
        MonitorAgentFactory._configure_notification_system(notification_system, settings)
        return notification_system