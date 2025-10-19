"""Alert management with routing and escalation logic."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from collections import defaultdict
from dataclasses import dataclass

from .monitoring_interfaces import (
    Alert, AlertType, ErrorSeverity, NotificationChannel, NotificationTool
)


logger = logging.getLogger(__name__)


@dataclass
class EscalationRule:
    """Defines escalation rules for alerts."""
    severity_threshold: ErrorSeverity
    initial_channels: List[NotificationChannel]
    escalation_delay: timedelta
    escalation_channels: List[NotificationChannel]
    max_escalations: int = 3
    escalation_multiplier: float = 2.0  # Multiply delay by this factor for each escalation


@dataclass
class AlertRoute:
    """Defines routing rules for alerts."""
    alert_type: AlertType
    severity_threshold: ErrorSeverity
    channels: List[NotificationChannel]
    throttle_minutes: int = 5
    enabled: bool = True


class AlertManager:
    """Manages alert routing, escalation, and throttling."""
    
    def __init__(self, notification_system: NotificationTool):
        self.notification_system = notification_system
        self._alert_routes: List[AlertRoute] = []
        self._escalation_rules: List[EscalationRule] = []
        self._active_alerts: Dict[str, Alert] = {}
        self._escalation_tasks: Dict[str, asyncio.Task] = {}
        self._alert_history: List[Dict[str, Any]] = []
        self._throttle_cache: Dict[str, datetime] = {}
        self._setup_default_routes()
        self._setup_default_escalation_rules()
    
    def _setup_default_routes(self) -> None:
        """Set up default alert routing rules."""
        self._alert_routes = [
            # Critical alerts - immediate notification via all channels
            AlertRoute(
                alert_type=AlertType.ERROR,
                severity_threshold=ErrorSeverity.CRITICAL,
                channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
                throttle_minutes=1,
                enabled=True
            ),
            AlertRoute(
                alert_type=AlertType.UPTIME,
                severity_threshold=ErrorSeverity.CRITICAL,
                channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
                throttle_minutes=1,
                enabled=True
            ),
            
            # High severity alerts - email and Slack
            AlertRoute(
                alert_type=AlertType.ERROR,
                severity_threshold=ErrorSeverity.HIGH,
                channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
                throttle_minutes=5,
                enabled=True
            ),
            AlertRoute(
                alert_type=AlertType.UPTIME,
                severity_threshold=ErrorSeverity.HIGH,
                channels=[NotificationChannel.EMAIL],
                throttle_minutes=5,
                enabled=True
            ),
            AlertRoute(
                alert_type=AlertType.SECURITY,
                severity_threshold=ErrorSeverity.HIGH,
                channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
                throttle_minutes=2,
                enabled=True
            ),
            
            # Medium severity alerts - email only
            AlertRoute(
                alert_type=AlertType.ERROR,
                severity_threshold=ErrorSeverity.MEDIUM,
                channels=[NotificationChannel.EMAIL],
                throttle_minutes=10,
                enabled=True
            ),
            AlertRoute(
                alert_type=AlertType.PERFORMANCE,
                severity_threshold=ErrorSeverity.MEDIUM,
                channels=[NotificationChannel.EMAIL],
                throttle_minutes=15,
                enabled=True
            ),
            
            # Low severity alerts - webhook only (for logging/tracking)
            AlertRoute(
                alert_type=AlertType.ERROR,
                severity_threshold=ErrorSeverity.LOW,
                channels=[NotificationChannel.WEBHOOK],
                throttle_minutes=30,
                enabled=True
            )
        ]
    
    def _setup_default_escalation_rules(self) -> None:
        """Set up default escalation rules."""
        self._escalation_rules = [
            # Critical alerts - escalate quickly
            EscalationRule(
                severity_threshold=ErrorSeverity.CRITICAL,
                initial_channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
                escalation_delay=timedelta(minutes=5),
                escalation_channels=[NotificationChannel.SMS, NotificationChannel.WEBHOOK],
                max_escalations=3,
                escalation_multiplier=1.5
            ),
            
            # High severity alerts - escalate after longer delay
            EscalationRule(
                severity_threshold=ErrorSeverity.HIGH,
                initial_channels=[NotificationChannel.EMAIL],
                escalation_delay=timedelta(minutes=15),
                escalation_channels=[NotificationChannel.SLACK],
                max_escalations=2,
                escalation_multiplier=2.0
            )
        ]
    
    async def process_alert(self, alert: Alert) -> Dict[str, Any]:
        """Process an alert through routing and escalation logic."""
        alert_key = self._get_alert_key(alert)
        
        # Check if alert is throttled
        if self._is_throttled(alert_key, alert):
            logger.info(f"Alert throttled: {alert.title}")
            return {
                "alert_id": alert.id,
                "processed": False,
                "reason": "throttled",
                "throttled_until": self._throttle_cache.get(alert_key, datetime.utcnow()).isoformat()
            }
        
        # Find matching routes
        matching_routes = self._find_matching_routes(alert)
        if not matching_routes:
            logger.warning(f"No matching routes found for alert: {alert.title}")
            return {
                "alert_id": alert.id,
                "processed": False,
                "reason": "no_matching_routes"
            }
        
        # Send initial notifications
        notification_results = {}
        all_channels = set()
        
        for route in matching_routes:
            if not route.enabled:
                continue
            
            for channel in route.channels:
                all_channels.add(channel)
        
        # Send notifications
        if all_channels:
            results = await self.notification_system.send_alert(alert, list(all_channels))
            notification_results.update(results)
        
        # Store active alert for potential escalation
        self._active_alerts[alert.id] = alert
        
        # Set up escalation if applicable
        escalation_rule = self._find_escalation_rule(alert)
        if escalation_rule and any(notification_results.values()):
            await self._setup_escalation(alert, escalation_rule)
        
        # Update throttle cache
        self._update_throttle_cache(alert_key, alert, matching_routes)
        
        # Record in history
        self._record_alert_processing(alert, notification_results, matching_routes)
        
        logger.info(f"Alert processed: {alert.title} - Sent to {len(all_channels)} channels")
        
        return {
            "alert_id": alert.id,
            "processed": True,
            "channels_notified": list(all_channels),
            "notification_results": notification_results,
            "escalation_scheduled": escalation_rule is not None
        }
    
    async def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an active alert and cancel any pending escalations."""
        if alert_id not in self._active_alerts:
            return False
        
        # Cancel escalation task if exists
        if alert_id in self._escalation_tasks:
            task = self._escalation_tasks[alert_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self._escalation_tasks[alert_id]
        
        # Mark alert as resolved
        alert = self._active_alerts[alert_id]
        alert.resolved_at = datetime.utcnow()
        
        # Remove from active alerts
        del self._active_alerts[alert_id]
        
        logger.info(f"Alert resolved: {alert.title}")
        return True
    
    def add_alert_route(self, route: AlertRoute) -> None:
        """Add a custom alert route."""
        self._alert_routes.append(route)
        logger.info(f"Added alert route for {route.alert_type.value} alerts with {route.severity_threshold.value} severity")
    
    def add_escalation_rule(self, rule: EscalationRule) -> None:
        """Add a custom escalation rule."""
        self._escalation_rules.append(rule)
        logger.info(f"Added escalation rule for {rule.severity_threshold.value} severity alerts")
    
    def _find_matching_routes(self, alert: Alert) -> List[AlertRoute]:
        """Find alert routes that match the given alert."""
        matching_routes = []
        
        for route in self._alert_routes:
            # Check alert type match
            if route.alert_type != alert.type:
                continue
            
            # Check severity threshold
            if self._severity_level(alert.severity) < self._severity_level(route.severity_threshold):
                continue
            
            matching_routes.append(route)
        
        return matching_routes
    
    def _find_escalation_rule(self, alert: Alert) -> Optional[EscalationRule]:
        """Find escalation rule that matches the given alert."""
        for rule in self._escalation_rules:
            if self._severity_level(alert.severity) >= self._severity_level(rule.severity_threshold):
                return rule
        return None
    
    async def _setup_escalation(self, alert: Alert, rule: EscalationRule) -> None:
        """Set up escalation for an alert."""
        escalation_task = asyncio.create_task(
            self._escalation_worker(alert, rule)
        )
        self._escalation_tasks[alert.id] = escalation_task
        
        logger.info(f"Escalation scheduled for alert {alert.id} in {rule.escalation_delay}")
    
    async def _escalation_worker(self, alert: Alert, rule: EscalationRule) -> None:
        """Worker task that handles alert escalation."""
        escalation_count = 0
        delay = rule.escalation_delay
        
        try:
            while escalation_count < rule.max_escalations:
                # Wait for escalation delay
                await asyncio.sleep(delay.total_seconds())
                
                # Check if alert is still active (not resolved)
                if alert.id not in self._active_alerts:
                    logger.info(f"Alert {alert.id} resolved before escalation")
                    return
                
                escalation_count += 1
                
                # Create escalation alert
                escalation_alert = Alert(
                    id=f"{alert.id}_escalation_{escalation_count}",
                    type=alert.type,
                    severity=alert.severity,
                    title=f"ESCALATION {escalation_count}: {alert.title}",
                    message=f"Alert has not been resolved after {delay}. Original: {alert.message}",
                    url=alert.url,
                    metadata={
                        **alert.metadata,
                        "escalation_level": escalation_count,
                        "original_alert_id": alert.id,
                        "escalation_reason": "unresolved_alert"
                    }
                )
                
                # Send escalation notification
                results = await self.notification_system.send_alert(
                    escalation_alert, 
                    rule.escalation_channels
                )
                
                logger.warning(f"Alert escalated (level {escalation_count}): {alert.title}")
                
                # Increase delay for next escalation
                delay = timedelta(seconds=delay.total_seconds() * rule.escalation_multiplier)
                
        except asyncio.CancelledError:
            logger.info(f"Escalation cancelled for alert {alert.id}")
        except Exception as e:
            logger.error(f"Error in escalation worker for alert {alert.id}: {str(e)}")
    
    def _get_alert_key(self, alert: Alert) -> str:
        """Generate a key for alert throttling."""
        return f"{alert.url}_{alert.type.value}_{alert.severity.value}"
    
    def _is_throttled(self, alert_key: str, alert: Alert) -> bool:
        """Check if an alert is throttled."""
        if alert_key not in self._throttle_cache:
            return False
        
        throttle_until = self._throttle_cache[alert_key]
        if datetime.utcnow() >= throttle_until:
            del self._throttle_cache[alert_key]
            return False
        
        return True
    
    def _update_throttle_cache(self, alert_key: str, alert: Alert, routes: List[AlertRoute]) -> None:
        """Update throttle cache for an alert."""
        if not routes:
            return
        
        # Use the minimum throttle time from matching routes
        min_throttle_minutes = min(route.throttle_minutes for route in routes)
        throttle_until = datetime.utcnow() + timedelta(minutes=min_throttle_minutes)
        self._throttle_cache[alert_key] = throttle_until
    
    def _severity_level(self, severity: ErrorSeverity) -> int:
        """Convert severity to numeric level for comparison."""
        levels = {
            ErrorSeverity.LOW: 1,
            ErrorSeverity.MEDIUM: 2,
            ErrorSeverity.HIGH: 3,
            ErrorSeverity.CRITICAL: 4
        }
        return levels.get(severity, 2)
    
    def _record_alert_processing(self, alert: Alert, results: Dict[str, bool], routes: List[AlertRoute]) -> None:
        """Record alert processing in history."""
        record = {
            "alert_id": alert.id,
            "alert_type": alert.type.value,
            "severity": alert.severity.value,
            "title": alert.title,
            "url": alert.url,
            "processed_at": datetime.utcnow().isoformat(),
            "routes_matched": len(routes),
            "channels_attempted": list(results.keys()),
            "channels_successful": [ch for ch, success in results.items() if success],
            "escalation_scheduled": alert.id in self._escalation_tasks
        }
        
        self._alert_history.append(record)
        
        # Keep only last 1000 records
        if len(self._alert_history) > 1000:
            self._alert_history = self._alert_history[-1000:]
    
    def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alert management statistics."""
        if not self._alert_history:
            return {
                "total_alerts_processed": 0,
                "active_alerts": 0,
                "pending_escalations": 0,
                "throttled_alerts": 0
            }
        
        total_processed = len(self._alert_history)
        active_alerts = len(self._active_alerts)
        pending_escalations = len(self._escalation_tasks)
        throttled_alerts = len(self._throttle_cache)
        
        # Calculate success rates
        successful_notifications = sum(
            1 for record in self._alert_history 
            if record["channels_successful"]
        )
        success_rate = (successful_notifications / total_processed * 100) if total_processed > 0 else 0
        
        # Severity distribution
        severity_dist = defaultdict(int)
        for record in self._alert_history:
            severity_dist[record["severity"]] += 1
        
        return {
            "total_alerts_processed": total_processed,
            "active_alerts": active_alerts,
            "pending_escalations": pending_escalations,
            "throttled_alerts": throttled_alerts,
            "notification_success_rate": success_rate,
            "severity_distribution": dict(severity_dist),
            "configured_routes": len(self._alert_routes),
            "configured_escalation_rules": len(self._escalation_rules)
        }
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get list of currently active alerts."""
        return [
            {
                "alert_id": alert.id,
                "type": alert.type.value,
                "severity": alert.severity.value,
                "title": alert.title,
                "url": alert.url,
                "triggered_at": alert.triggered_at.isoformat(),
                "has_escalation": alert.id in self._escalation_tasks
            }
            for alert in self._active_alerts.values()
        ]
    
    async def cleanup(self) -> None:
        """Clean up resources and cancel pending tasks."""
        # Cancel all escalation tasks
        for alert_id, task in self._escalation_tasks.items():
            if not task.done():
                task.cancel()
                logger.info(f"Cancelled escalation task for alert {alert_id}")
        
        # Wait for tasks to complete
        if self._escalation_tasks:
            await asyncio.gather(*self._escalation_tasks.values(), return_exceptions=True)
        
        self._escalation_tasks.clear()
        logger.info("Alert manager cleanup completed")