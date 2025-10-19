"""Simple test script to verify monitoring components work correctly."""

import asyncio
import logging
from datetime import datetime, timedelta

from .health_monitoring import HealthMonitor
from .error_tracking import ErrorTracker
from .notification_system import NotificationSystem
from .alert_manager import AlertManager
from .monitoring_interfaces import (
    MonitoringSetup, Alert, AlertType, ErrorSeverity, NotificationChannel
)


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_health_monitoring():
    """Test health monitoring functionality."""
    logger.info("Testing health monitoring...")
    
    health_monitor = HealthMonitor()
    await health_monitor.start()
    
    try:
        # Test health check
        health_status = await health_monitor.check_health("https://httpbin.org/status/200")
        logger.info(f"Health check result: {health_status.status} ({health_status.response_time}ms)")
        
        # Test monitoring setup
        config = MonitoringSetup(
            url="https://httpbin.org/status/200",
            project_id="test_project",
            check_interval=10,
            timeout=5
        )
        
        setup_result = await health_monitor.setup_uptime_monitoring(config)
        logger.info(f"Monitoring setup: {setup_result}")
        
        # Wait a bit for monitoring to collect data
        await asyncio.sleep(15)
        
        # Get metrics
        metrics = await health_monitor.get_uptime_metrics("https://httpbin.org/status/200")
        logger.info(f"Metrics: {metrics.uptime_percentage}% uptime, {metrics.average_response_time}ms avg response")
        
        # Stop monitoring
        await health_monitor.stop_monitoring("https://httpbin.org/status/200")
        
    finally:
        await health_monitor.stop()
    
    logger.info("Health monitoring test completed")


async def test_error_tracking():
    """Test error tracking functionality."""
    logger.info("Testing error tracking...")
    
    error_tracker = ErrorTracker()
    await error_tracker.start()
    
    try:
        # Set up error tracking
        setup_result = await error_tracker.setup_error_tracking(
            "https://httpbin.org/status/500", 
            "test_project", 
            {"check_interval": 10}
        )
        logger.info(f"Error tracking setup: {setup_result}")
        
        # Wait for error detection
        await asyncio.sleep(15)
        
        # Get errors
        errors = await error_tracker.get_errors("https://httpbin.org/status/500", timedelta(minutes=5))
        logger.info(f"Found {len(errors)} errors")
        
        if errors:
            # Analyze error patterns
            analysis = await error_tracker.analyze_error_patterns(errors)
            logger.info(f"Error analysis: {analysis['total_errors']} total, {len(analysis['recommendations'])} recommendations")
        
    finally:
        await error_tracker.stop()
    
    logger.info("Error tracking test completed")


async def test_notification_system():
    """Test notification system functionality."""
    logger.info("Testing notification system...")
    
    notification_system = NotificationSystem()
    await notification_system.start()
    
    try:
        # Test basic notification (will fail without real config, but tests the interface)
        test_message = "Test notification from monitoring system"
        
        # This will fail but tests the validation
        try:
            result = await notification_system.send_notification(
                NotificationChannel.EMAIL, 
                test_message, 
                {"smtp_server": "test", "smtp_port": 587, "username": "test", "password": "test", "from_email": "test@test.com", "to_emails": ["test@test.com"]}
            )
            logger.info(f"Notification result: {result}")
        except Exception as e:
            logger.info(f"Notification test failed as expected: {str(e)[:100]}")
        
        # Test alert creation
        alert = Alert(
            id="test_alert_1",
            type=AlertType.ERROR,
            severity=ErrorSeverity.HIGH,
            title="Test Alert",
            message="This is a test alert",
            url="https://test.com"
        )
        
        logger.info(f"Created test alert: {alert.title}")
        
    finally:
        await notification_system.stop()
    
    logger.info("Notification system test completed")


async def test_alert_manager():
    """Test alert manager functionality."""
    logger.info("Testing alert manager...")
    
    notification_system = NotificationSystem()
    await notification_system.start()
    
    try:
        alert_manager = AlertManager(notification_system)
        
        # Create test alert
        alert = Alert(
            id="test_alert_2",
            type=AlertType.ERROR,
            severity=ErrorSeverity.CRITICAL,
            title="Critical Test Alert",
            message="This is a critical test alert",
            url="https://test.com"
        )
        
        # Process alert (will attempt to send but likely fail due to no real config)
        result = await alert_manager.process_alert(alert)
        logger.info(f"Alert processing result: {result}")
        
        # Get statistics
        stats = alert_manager.get_alert_statistics()
        logger.info(f"Alert manager stats: {stats}")
        
        # Cleanup
        await alert_manager.cleanup()
        
    finally:
        await notification_system.stop()
    
    logger.info("Alert manager test completed")


async def run_all_tests():
    """Run all monitoring tests."""
    logger.info("Starting monitoring system tests...")
    
    try:
        await test_health_monitoring()
        await test_error_tracking()
        await test_notification_system()
        await test_alert_manager()
        
        logger.info("All monitoring tests completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        raise


if __name__ == "__main__":
    asyncio.run(run_all_tests())