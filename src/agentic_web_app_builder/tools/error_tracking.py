"""Error tracking and analysis implementation."""

import asyncio
import aiohttp
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from collections import defaultdict, Counter

from .monitoring_interfaces import (
    ErrorTrackingTool, ErrorEvent, ErrorSeverity
)
from .log_analyzer import LogAnalyzer


logger = logging.getLogger(__name__)


class ErrorTracker(ErrorTrackingTool):
    """Implementation of error tracking and analysis."""
    
    def __init__(self):
        self._error_storage: Dict[str, List[ErrorEvent]] = defaultdict(list)
        self._error_patterns: Dict[str, Dict[str, Any]] = {}
        self._severity_rules: List[Dict[str, Any]] = []
        self._setup_default_severity_rules()
        self.session: Optional[aiohttp.ClientSession] = None
        self.log_analyzer = LogAnalyzer()
    
    async def start(self) -> None:
        """Start the error tracking service."""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        logger.info("Error tracker started")
    
    async def stop(self) -> None:
        """Stop the error tracking service."""
        if self.session:
            await self.session.close()
            self.session = None
        logger.info("Error tracker stopped")
    
    def _setup_default_severity_rules(self) -> None:
        """Set up default rules for error severity classification."""
        self._severity_rules = [
            # Critical errors
            {
                "pattern": r"5\d\d",  # 5xx HTTP errors
                "field": "error_type",
                "severity": ErrorSeverity.CRITICAL,
                "description": "Server errors"
            },
            {
                "pattern": r"database.*connection.*failed",
                "field": "message",
                "severity": ErrorSeverity.CRITICAL,
                "description": "Database connection failures"
            },
            {
                "pattern": r"out of memory|memory.*exhausted",
                "field": "message",
                "severity": ErrorSeverity.CRITICAL,
                "description": "Memory issues"
            },
            
            # High severity errors
            {
                "pattern": r"4\d\d",  # 4xx HTTP errors
                "field": "error_type",
                "severity": ErrorSeverity.HIGH,
                "description": "Client errors"
            },
            {
                "pattern": r"uncaught.*exception|unhandled.*error",
                "field": "message",
                "severity": ErrorSeverity.HIGH,
                "description": "Unhandled exceptions"
            },
            {
                "pattern": r"authentication.*failed|unauthorized",
                "field": "message",
                "severity": ErrorSeverity.HIGH,
                "description": "Authentication failures"
            },
            
            # Medium severity errors
            {
                "pattern": r"timeout|timed.*out",
                "field": "message",
                "severity": ErrorSeverity.MEDIUM,
                "description": "Timeout errors"
            },
            {
                "pattern": r"validation.*error|invalid.*input",
                "field": "message",
                "severity": ErrorSeverity.MEDIUM,
                "description": "Validation errors"
            },
            
            # Low severity errors
            {
                "pattern": r"warning|deprecated",
                "field": "message",
                "severity": ErrorSeverity.LOW,
                "description": "Warnings and deprecations"
            },
            {
                "pattern": r"404",
                "field": "error_type",
                "severity": ErrorSeverity.LOW,
                "description": "Not found errors"
            }
        ]
    
    async def setup_error_tracking(self, url: str, project_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Set up error tracking for an application."""
        if not self.session:
            await self.start()
        
        # Initialize error storage for this URL
        if url not in self._error_storage:
            self._error_storage[url] = []
        
        # Store configuration
        tracking_config = {
            "url": url,
            "project_id": project_id,
            "enabled": True,
            "setup_time": datetime.utcnow().isoformat(),
            "config": config
        }
        
        # Start basic error detection by checking for common error pages
        asyncio.create_task(self._start_basic_error_detection(url, project_id))
        
        logger.info(f"Error tracking setup completed for {url} (project: {project_id})")
        
        return tracking_config
    
    async def get_errors(self, url: str, time_period: timedelta = timedelta(hours=24)) -> List[ErrorEvent]:
        """Get errors for a URL over a time period."""
        if url not in self._error_storage:
            return []
        
        cutoff_time = datetime.utcnow() - time_period
        recent_errors = [
            error for error in self._error_storage[url]
            if error.timestamp >= cutoff_time
        ]
        
        # Sort by timestamp (most recent first)
        recent_errors.sort(key=lambda x: x.timestamp, reverse=True)
        
        return recent_errors
    
    async def analyze_error_patterns(self, errors: List[ErrorEvent]) -> Dict[str, Any]:
        """Analyze error patterns and trends."""
        if not errors:
            return {
                "total_errors": 0,
                "patterns": {},
                "trends": {},
                "recommendations": []
            }
        
        # Group errors by type
        error_types = Counter(error.error_type for error in errors)
        
        # Group errors by severity
        severity_counts = Counter(error.severity.value for error in errors)
        
        # Analyze time patterns
        hourly_counts = defaultdict(int)
        for error in errors:
            hour = error.timestamp.hour
            hourly_counts[hour] += 1
        
        # Find most common error messages
        message_patterns = Counter()
        for error in errors:
            # Extract key parts of error messages
            message_words = re.findall(r'\w+', error.message.lower())
            for word in message_words:
                if len(word) > 3:  # Ignore short words
                    message_patterns[word] += 1
        
        # Calculate error rate trends
        now = datetime.utcnow()
        last_hour_errors = len([e for e in errors if e.timestamp >= now - timedelta(hours=1)])
        last_day_errors = len([e for e in errors if e.timestamp >= now - timedelta(days=1)])
        
        # Generate recommendations
        recommendations = self._generate_recommendations(errors, error_types, severity_counts)
        
        analysis = {
            "total_errors": len(errors),
            "time_range": {
                "start": min(error.timestamp for error in errors).isoformat(),
                "end": max(error.timestamp for error in errors).isoformat()
            },
            "patterns": {
                "error_types": dict(error_types.most_common(10)),
                "severity_distribution": dict(severity_counts),
                "hourly_distribution": dict(hourly_counts),
                "common_message_words": dict(message_patterns.most_common(10))
            },
            "trends": {
                "last_hour_count": last_hour_errors,
                "last_day_count": last_day_errors,
                "average_per_hour": last_day_errors / 24 if last_day_errors > 0 else 0
            },
            "recommendations": recommendations
        }
        
        return analysis
    
    async def categorize_error(self, error: ErrorEvent) -> ErrorSeverity:
        """Categorize an error by severity using predefined rules."""
        for rule in self._severity_rules:
            field_value = getattr(error, rule["field"], "")
            if isinstance(field_value, str) and re.search(rule["pattern"], field_value, re.IGNORECASE):
                logger.debug(f"Error categorized as {rule['severity'].value}: {rule['description']}")
                return rule["severity"]
        
        # Default to medium severity if no rules match
        return ErrorSeverity.MEDIUM
    
    async def resolve_error(self, error_id: str) -> bool:
        """Mark an error as resolved."""
        for url_errors in self._error_storage.values():
            for error in url_errors:
                if error.id == error_id:
                    error.resolved = True
                    logger.info(f"Error {error_id} marked as resolved")
                    return True
        
        logger.warning(f"Error {error_id} not found for resolution")
        return False
    
    async def _start_basic_error_detection(self, url: str, project_id: str) -> None:
        """Start basic error detection by periodically checking the URL."""
        try:
            while True:
                await self._check_for_errors(url, project_id)
                await asyncio.sleep(300)  # Check every 5 minutes
        except asyncio.CancelledError:
            logger.info(f"Error detection cancelled for {url}")
        except Exception as e:
            logger.error(f"Error in basic error detection for {url}: {str(e)}")
    
    async def _check_for_errors(self, url: str, project_id: str) -> None:
        """Check a URL for common errors."""
        if not self.session:
            return
        
        try:
            async with self.session.get(url) as response:
                # Check for HTTP error status codes
                if response.status >= 400:
                    error_event = ErrorEvent(
                        id=f"{url}_{response.status}_{datetime.utcnow().isoformat()}",
                        url=url,
                        error_type=str(response.status),
                        message=f"HTTP {response.status}: {response.reason}",
                        timestamp=datetime.utcnow(),
                        severity=await self._classify_http_error(response.status)
                    )
                    
                    await self._store_error(url, error_event)
                
                # Check response content for JavaScript errors (basic detection)
                if response.content_type and "text/html" in response.content_type:
                    content = await response.text()
                    await self._detect_client_side_errors(url, content)
                    
        except aiohttp.ClientError as e:
            # Network or connection errors
            error_event = ErrorEvent(
                id=f"{url}_connection_{datetime.utcnow().isoformat()}",
                url=url,
                error_type="connection_error",
                message=f"Connection error: {str(e)}",
                timestamp=datetime.utcnow(),
                severity=ErrorSeverity.HIGH
            )
            
            await self._store_error(url, error_event)
            
        except Exception as e:
            logger.error(f"Unexpected error checking {url}: {str(e)}")
    
    async def _classify_http_error(self, status_code: int) -> ErrorSeverity:
        """Classify HTTP error by status code."""
        if status_code >= 500:
            return ErrorSeverity.CRITICAL
        elif status_code >= 400:
            if status_code == 404:
                return ErrorSeverity.LOW
            elif status_code in [401, 403]:
                return ErrorSeverity.HIGH
            else:
                return ErrorSeverity.MEDIUM
        else:
            return ErrorSeverity.LOW
    
    async def _detect_client_side_errors(self, url: str, content: str) -> None:
        """Detect potential client-side errors in HTML content."""
        # Look for common error indicators in HTML
        error_indicators = [
            (r"javascript.*error", "JavaScript error detected"),
            (r"uncaught.*exception", "Uncaught exception detected"),
            (r"404.*not.*found", "404 error page detected"),
            (r"500.*internal.*server.*error", "500 error page detected"),
            (r"error.*occurred", "Generic error message detected")
        ]
        
        for pattern, description in error_indicators:
            if re.search(pattern, content, re.IGNORECASE):
                error_event = ErrorEvent(
                    id=f"{url}_client_{datetime.utcnow().isoformat()}",
                    url=url,
                    error_type="client_side_error",
                    message=description,
                    timestamp=datetime.utcnow(),
                    severity=ErrorSeverity.MEDIUM
                )
                
                await self._store_error(url, error_event)
    
    async def _store_error(self, url: str, error: ErrorEvent) -> None:
        """Store an error event."""
        # Check for duplicate errors (same type and message within 5 minutes)
        recent_cutoff = datetime.utcnow() - timedelta(minutes=5)
        recent_errors = [
            e for e in self._error_storage[url]
            if e.timestamp >= recent_cutoff and e.error_type == error.error_type and e.message == error.message
        ]
        
        if recent_errors:
            # Update existing error count instead of creating duplicate
            existing_error = recent_errors[0]
            existing_error.count += 1
            existing_error.last_seen = error.timestamp
            logger.debug(f"Updated error count for {error.error_type}: {existing_error.count}")
        else:
            # Categorize the error
            error.severity = await self.categorize_error(error)
            
            # Store new error
            self._error_storage[url].append(error)
            
            # Keep only last 1000 errors per URL
            if len(self._error_storage[url]) > 1000:
                self._error_storage[url] = self._error_storage[url][-1000:]
            
            logger.info(f"Stored new error for {url}: {error.error_type} - {error.message}")
    
    def _generate_recommendations(self, errors: List[ErrorEvent], error_types: Counter, severity_counts: Counter) -> List[str]:
        """Generate recommendations based on error analysis."""
        recommendations = []
        
        # High error count recommendations
        if len(errors) > 100:
            recommendations.append("High error volume detected. Consider implementing error rate limiting or circuit breakers.")
        
        # Severity-based recommendations
        critical_count = severity_counts.get("critical", 0)
        if critical_count > 0:
            recommendations.append(f"Found {critical_count} critical errors. Immediate attention required.")
        
        # Error type specific recommendations
        if "500" in error_types or "502" in error_types or "503" in error_types:
            recommendations.append("Server errors detected. Check server health, resources, and dependencies.")
        
        if "404" in error_types and error_types["404"] > 10:
            recommendations.append("Multiple 404 errors found. Review URL routing and broken links.")
        
        if "timeout" in str(error_types):
            recommendations.append("Timeout errors detected. Consider optimizing response times or increasing timeout limits.")
        
        # Pattern-based recommendations
        connection_errors = sum(1 for error in errors if "connection" in error.error_type.lower())
        if connection_errors > 5:
            recommendations.append("Multiple connection errors. Check network connectivity and DNS resolution.")
        
        if not recommendations:
            recommendations.append("Error patterns look normal. Continue monitoring for trends.")
        
        return recommendations
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """Validate error tracking parameters."""
        url = parameters.get("url")
        project_id = parameters.get("project_id")
        return bool(url and project_id)
    
    async def analyze_logs(self, url: str, log_entries: List[str], time_window: Optional[timedelta] = None) -> Dict[str, Any]:
        """Analyze log entries and extract error events."""
        if not log_entries:
            return {
                "error_events_created": 0,
                "log_analysis": None,
                "patterns_detected": []
            }
        
        # Perform log analysis
        analysis_result = await self.log_analyzer.analyze_logs(log_entries, time_window)
        
        # Convert log entries to error events
        error_events = await self.log_analyzer.create_error_events_from_logs(log_entries, url)
        
        # Store error events
        for error_event in error_events:
            await self._store_error(url, error_event)
        
        logger.info(f"Analyzed {len(log_entries)} log entries, created {len(error_events)} error events")
        
        return {
            "error_events_created": len(error_events),
            "log_analysis": {
                "total_entries": analysis_result.total_entries,
                "error_entries": analysis_result.error_entries,
                "warning_entries": analysis_result.warning_entries,
                "patterns_detected": len(analysis_result.patterns_detected),
                "anomalies_detected": len(analysis_result.anomalies),
                "recommendations": analysis_result.recommendations
            },
            "patterns_detected": [
                {
                    "pattern": pattern.pattern,
                    "description": pattern.description,
                    "severity": pattern.severity.value,
                    "frequency": pattern.frequency
                }
                for pattern in analysis_result.patterns_detected
            ]
        }
    
    async def get_log_analysis_report(self, url: str, time_period: timedelta = timedelta(hours=24)) -> Dict[str, Any]:
        """Generate a comprehensive log analysis report."""
        # Get recent errors
        recent_errors = await self.get_errors(url, time_period)
        
        if not recent_errors:
            return {
                "url": url,
                "time_period_hours": time_period.total_seconds() / 3600,
                "error_count": 0,
                "report": "No errors found in the specified time period"
            }
        
        # Convert errors back to log-like format for analysis
        log_entries = []
        for error in recent_errors:
            log_entry = f"{error.timestamp.isoformat()} {error.severity.value.upper()} {error.error_type}: {error.message}"
            log_entries.append(log_entry)
        
        # Perform analysis
        analysis_result = await self.log_analyzer.analyze_logs(log_entries, time_period)
        
        return {
            "url": url,
            "time_period_hours": time_period.total_seconds() / 3600,
            "error_count": len(recent_errors),
            "analysis": {
                "total_entries": analysis_result.total_entries,
                "error_entries": analysis_result.error_entries,
                "warning_entries": analysis_result.warning_entries,
                "info_entries": analysis_result.info_entries,
                "patterns_detected": [
                    {
                        "pattern": p.pattern,
                        "description": p.description,
                        "severity": p.severity.value,
                        "frequency": p.frequency,
                        "first_seen": p.first_seen.isoformat(),
                        "last_seen": p.last_seen.isoformat(),
                        "examples": p.examples[:3]  # Limit examples
                    }
                    for p in analysis_result.patterns_detected
                ],
                "anomalies": analysis_result.anomalies,
                "recommendations": analysis_result.recommendations
            },
            "generated_at": datetime.utcnow().isoformat()
        }
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get overall error tracking statistics."""
        total_errors = sum(len(errors) for errors in self._error_storage.values())
        monitored_urls = len(self._error_storage)
        
        # Calculate severity distribution across all errors
        all_errors = []
        for errors in self._error_storage.values():
            all_errors.extend(errors)
        
        severity_dist = Counter(error.severity.value for error in all_errors)
        
        return {
            "total_errors": total_errors,
            "monitored_urls": monitored_urls,
            "severity_distribution": dict(severity_dist),
            "urls": list(self._error_storage.keys())
        }