"""Notification system implementation for alerts and monitoring."""

import asyncio
import aiohttp
import smtplib
import logging
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List, Optional
from collections import defaultdict

from .monitoring_interfaces import (
    NotificationTool, NotificationChannel, Alert, ErrorSeverity
)


logger = logging.getLogger(__name__)


class NotificationSystem(NotificationTool):
    """Implementation of notification system for alerts and monitoring."""
    
    def __init__(self):
        self._channel_configs: Dict[NotificationChannel, Dict[str, Any]] = {}
        self._notification_history: List[Dict[str, Any]] = []
        self._throttle_cache: Dict[str, datetime] = {}
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def start(self) -> None:
        """Start the notification system."""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        logger.info("Notification system started")
    
    async def stop(self) -> None:
        """Stop the notification system."""
        if self.session:
            await self.session.close()
            self.session = None
        logger.info("Notification system stopped")
    
    async def send_notification(self, channel: NotificationChannel, message: str, config: Dict[str, Any]) -> bool:
        """Send a notification through the specified channel."""
        try:
            if channel == NotificationChannel.EMAIL:
                return await self._send_email(message, config)
            elif channel == NotificationChannel.SLACK:
                return await self._send_slack(message, config)
            elif channel == NotificationChannel.WEBHOOK:
                return await self._send_webhook(message, config)
            elif channel == NotificationChannel.SMS:
                return await self._send_sms(message, config)
            else:
                logger.error(f"Unsupported notification channel: {channel}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send notification via {channel.value}: {str(e)}")
            return False
    
    async def send_alert(self, alert: Alert, channels: List[NotificationChannel]) -> Dict[str, bool]:
        """Send an alert through multiple channels."""
        results = {}
        
        # Check throttling
        throttle_key = f"{alert.url}_{alert.type.value}_{alert.severity.value}"
        if self._is_throttled(throttle_key):
            logger.info(f"Alert throttled: {throttle_key}")
            return {channel.value: False for channel in channels}
        
        # Format alert message
        message = self._format_alert_message(alert)
        
        # Send through each channel
        for channel in channels:
            config = self._channel_configs.get(channel, {})
            if not config:
                logger.warning(f"No configuration found for channel {channel.value}")
                results[channel.value] = False
                continue
            
            # Check severity threshold
            threshold = config.get("severity_threshold", ErrorSeverity.MEDIUM)
            if isinstance(threshold, str):
                threshold = ErrorSeverity(threshold)
            
            if self._severity_level(alert.severity) < self._severity_level(threshold):
                logger.debug(f"Alert severity {alert.severity.value} below threshold {threshold.value} for {channel.value}")
                results[channel.value] = False
                continue
            
            # Send notification
            success = await self.send_notification(channel, message, config)
            results[channel.value] = success
            
            if success:
                alert.channels_notified.append(channel)
        
        # Update alert status
        alert.notification_sent = any(results.values())
        
        # Record in history
        self._record_notification(alert, results)
        
        # Update throttle cache
        if alert.notification_sent:
            throttle_minutes = min(config.get("throttle_minutes", 5) for config in self._channel_configs.values() if config)
            self._throttle_cache[throttle_key] = datetime.utcnow() + timedelta(minutes=throttle_minutes)
        
        return results
    
    async def configure_channel(self, channel: NotificationChannel, config: Dict[str, Any]) -> bool:
        """Configure a notification channel."""
        try:
            # Validate configuration based on channel type
            if channel == NotificationChannel.EMAIL:
                required_keys = ["smtp_server", "smtp_port", "username", "password", "from_email", "to_emails"]
                if not all(key in config for key in required_keys):
                    logger.error(f"Missing required configuration for email: {required_keys}")
                    return False
            
            elif channel == NotificationChannel.SLACK:
                required_keys = ["webhook_url"]
                if not all(key in config for key in required_keys):
                    logger.error(f"Missing required configuration for Slack: {required_keys}")
                    return False
            
            elif channel == NotificationChannel.WEBHOOK:
                required_keys = ["url"]
                if not all(key in config for key in required_keys):
                    logger.error(f"Missing required configuration for webhook: {required_keys}")
                    return False
            
            elif channel == NotificationChannel.SMS:
                required_keys = ["service", "api_key", "phone_numbers"]
                if not all(key in config for key in required_keys):
                    logger.error(f"Missing required configuration for SMS: {required_keys}")
                    return False
            
            # Store configuration
            self._channel_configs[channel] = config
            logger.info(f"Configured notification channel: {channel.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to configure channel {channel.value}: {str(e)}")
            return False
    
    async def test_channel(self, channel: NotificationChannel, config: Dict[str, Any]) -> bool:
        """Test a notification channel configuration."""
        test_message = f"Test notification from Agentic Web App Builder - {datetime.utcnow().isoformat()}"
        
        try:
            success = await self.send_notification(channel, test_message, config)
            if success:
                logger.info(f"Test notification successful for {channel.value}")
            else:
                logger.warning(f"Test notification failed for {channel.value}")
            return success
            
        except Exception as e:
            logger.error(f"Test notification error for {channel.value}: {str(e)}")
            return False
    
    async def _send_email(self, message: str, config: Dict[str, Any]) -> bool:
        """Send email notification."""
        try:
            smtp_server = config["smtp_server"]
            smtp_port = config["smtp_port"]
            username = config["username"]
            password = config["password"]
            from_email = config["from_email"]
            to_emails = config["to_emails"]
            
            if isinstance(to_emails, str):
                to_emails = [to_emails]
            
            # Create message
            msg = MIMEMultipart()
            msg["From"] = from_email
            msg["To"] = ", ".join(to_emails)
            msg["Subject"] = config.get("subject", "Alert from Agentic Web App Builder")
            
            # Add body
            body = MIMEText(message, "plain")
            msg.attach(body)
            
            # Send email
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(username, password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {len(to_emails)} recipients")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            return False
    
    async def _send_slack(self, message: str, config: Dict[str, Any]) -> bool:
        """Send Slack notification."""
        if not self.session:
            await self.start()
        
        try:
            webhook_url = config["webhook_url"]
            channel = config.get("channel", "#general")
            username = config.get("username", "Agentic Web App Builder")
            
            payload = {
                "text": message,
                "channel": channel,
                "username": username,
                "icon_emoji": config.get("icon_emoji", ":robot_face:")
            }
            
            async with self.session.post(webhook_url, json=payload) as response:
                if response.status == 200:
                    logger.info("Slack notification sent successfully")
                    return True
                else:
                    logger.error(f"Slack notification failed with status {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {str(e)}")
            return False
    
    async def _send_webhook(self, message: str, config: Dict[str, Any]) -> bool:
        """Send webhook notification."""
        if not self.session:
            await self.start()
        
        try:
            url = config["url"]
            method = config.get("method", "POST").upper()
            headers = config.get("headers", {"Content-Type": "application/json"})
            
            payload = {
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
                "source": "agentic_web_app_builder"
            }
            
            # Add custom payload fields
            if "payload_template" in config:
                payload.update(config["payload_template"])
            
            if method == "POST":
                async with self.session.post(url, json=payload, headers=headers) as response:
                    success = 200 <= response.status < 300
            elif method == "PUT":
                async with self.session.put(url, json=payload, headers=headers) as response:
                    success = 200 <= response.status < 300
            else:
                logger.error(f"Unsupported webhook method: {method}")
                return False
            
            if success:
                logger.info("Webhook notification sent successfully")
            else:
                logger.error(f"Webhook notification failed with status {response.status}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to send webhook notification: {str(e)}")
            return False
    
    async def _send_sms(self, message: str, config: Dict[str, Any]) -> bool:
        """Send SMS notification (placeholder implementation)."""
        # This is a placeholder implementation
        # In a real system, you would integrate with SMS services like Twilio, AWS SNS, etc.
        
        try:
            service = config["service"]
            api_key = config["api_key"]
            phone_numbers = config["phone_numbers"]
            
            if isinstance(phone_numbers, str):
                phone_numbers = [phone_numbers]
            
            logger.info(f"SMS notification would be sent to {len(phone_numbers)} numbers via {service}")
            logger.info(f"Message: {message[:100]}...")  # Log first 100 chars
            
            # Simulate successful SMS sending
            await asyncio.sleep(0.1)
            return True
            
        except Exception as e:
            logger.error(f"Failed to send SMS notification: {str(e)}")
            return False
    
    def _format_alert_message(self, alert: Alert) -> str:
        """Format an alert into a readable message."""
        severity_emoji = {
            ErrorSeverity.LOW: "ℹ️",
            ErrorSeverity.MEDIUM: "⚠️",
            ErrorSeverity.HIGH: "🚨",
            ErrorSeverity.CRITICAL: "🔥"
        }
        
        emoji = severity_emoji.get(alert.severity, "⚠️")
        
        message = f"{emoji} {alert.severity.value.upper()} ALERT: {alert.title}\n\n"
        message += f"URL: {alert.url}\n"
        message += f"Type: {alert.type.value}\n"
        message += f"Time: {alert.triggered_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
        message += f"Details: {alert.message}\n"
        
        if alert.metadata:
            message += "\nAdditional Information:\n"
            for key, value in alert.metadata.items():
                message += f"- {key}: {value}\n"
        
        return message
    
    def _is_throttled(self, throttle_key: str) -> bool:
        """Check if a notification is throttled."""
        if throttle_key not in self._throttle_cache:
            return False
        
        throttle_until = self._throttle_cache[throttle_key]
        if datetime.utcnow() >= throttle_until:
            del self._throttle_cache[throttle_key]
            return False
        
        return True
    
    def _severity_level(self, severity: ErrorSeverity) -> int:
        """Convert severity to numeric level for comparison."""
        levels = {
            ErrorSeverity.LOW: 1,
            ErrorSeverity.MEDIUM: 2,
            ErrorSeverity.HIGH: 3,
            ErrorSeverity.CRITICAL: 4
        }
        return levels.get(severity, 2)
    
    def _record_notification(self, alert: Alert, results: Dict[str, bool]) -> None:
        """Record notification in history."""
        record = {
            "alert_id": alert.id,
            "alert_type": alert.type.value,
            "severity": alert.severity.value,
            "url": alert.url,
            "timestamp": datetime.utcnow().isoformat(),
            "channels": results,
            "success": any(results.values())
        }
        
        self._notification_history.append(record)
        
        # Keep only last 1000 notifications
        if len(self._notification_history) > 1000:
            self._notification_history = self._notification_history[-1000:]
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """Validate notification parameters."""
        channel = parameters.get("channel")
        message = parameters.get("message")
        return bool(channel and message)
    
    def get_notification_statistics(self) -> Dict[str, Any]:
        """Get notification system statistics."""
        if not self._notification_history:
            return {
                "total_notifications": 0,
                "success_rate": 0,
                "configured_channels": list(self._channel_configs.keys()),
                "throttled_alerts": len(self._throttle_cache)
            }
        
        total = len(self._notification_history)
        successful = sum(1 for record in self._notification_history if record["success"])
        success_rate = (successful / total * 100) if total > 0 else 0
        
        # Channel usage statistics
        channel_usage = defaultdict(int)
        for record in self._notification_history:
            for channel, success in record["channels"].items():
                if success:
                    channel_usage[channel] += 1
        
        return {
            "total_notifications": total,
            "successful_notifications": successful,
            "success_rate": success_rate,
            "configured_channels": [ch.value for ch in self._channel_configs.keys()],
            "channel_usage": dict(channel_usage),
            "throttled_alerts": len(self._throttle_cache),
            "recent_notifications": self._notification_history[-10:]  # Last 10
        }