"""Advanced log analysis and pattern detection for monitoring."""

import re
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass

from .monitoring_interfaces import ErrorEvent, ErrorSeverity


logger = logging.getLogger(__name__)


@dataclass
class LogPattern:
    """Represents a detected pattern in logs."""
    pattern: str
    description: str
    severity: ErrorSeverity
    frequency: int
    first_seen: datetime
    last_seen: datetime
    examples: List[str]


@dataclass
class LogAnalysisResult:
    """Result of log analysis."""
    total_entries: int
    error_entries: int
    warning_entries: int
    info_entries: int
    patterns_detected: List[LogPattern]
    anomalies: List[Dict[str, Any]]
    recommendations: List[str]
    analysis_time: datetime


class LogAnalyzer:
    """Advanced log analyzer for detecting patterns and anomalies."""
    
    def __init__(self):
        self._known_patterns = self._initialize_patterns()
        self._log_history: List[Dict[str, Any]] = []
        self._pattern_cache: Dict[str, LogPattern] = {}
    
    def _initialize_patterns(self) -> List[Dict[str, Any]]:
        """Initialize known log patterns for detection."""
        return [
            # Error patterns
            {
                "pattern": r"ERROR|error|Error",
                "description": "General error messages",
                "severity": ErrorSeverity.HIGH,
                "category": "error"
            },
            {
                "pattern": r"FATAL|fatal|Fatal|CRITICAL|critical|Critical",
                "description": "Critical/fatal errors",
                "severity": ErrorSeverity.CRITICAL,
                "category": "critical"
            },
            {
                "pattern": r"exception|Exception|EXCEPTION",
                "description": "Exception occurrences",
                "severity": ErrorSeverity.HIGH,
                "category": "exception"
            },
            {
                "pattern": r"stack\s*trace|stacktrace|Stack\s*Trace",
                "description": "Stack trace indicators",
                "severity": ErrorSeverity.HIGH,
                "category": "stacktrace"
            },
            
            # Warning patterns
            {
                "pattern": r"WARN|warn|Warning|WARNING",
                "description": "Warning messages",
                "severity": ErrorSeverity.MEDIUM,
                "category": "warning"
            },
            {
                "pattern": r"deprecated|Deprecated|DEPRECATED",
                "description": "Deprecated feature usage",
                "severity": ErrorSeverity.LOW,
                "category": "deprecated"
            },
            
            # Performance patterns
            {
                "pattern": r"timeout|Timeout|TIMEOUT|timed\s*out",
                "description": "Timeout occurrences",
                "severity": ErrorSeverity.MEDIUM,
                "category": "timeout"
            },
            {
                "pattern": r"slow|Slow|SLOW|performance",
                "description": "Performance issues",
                "severity": ErrorSeverity.MEDIUM,
                "category": "performance"
            },
            {
                "pattern": r"memory|Memory|MEMORY|out\s*of\s*memory",
                "description": "Memory-related issues",
                "severity": ErrorSeverity.HIGH,
                "category": "memory"
            },
            
            # Security patterns
            {
                "pattern": r"unauthorized|Unauthorized|UNAUTHORIZED|403|401",
                "description": "Authorization failures",
                "severity": ErrorSeverity.HIGH,
                "category": "security"
            },
            {
                "pattern": r"authentication|Authentication|AUTHENTICATION|login\s*failed",
                "description": "Authentication issues",
                "severity": ErrorSeverity.HIGH,
                "category": "security"
            },
            
            # Database patterns
            {
                "pattern": r"database|Database|DATABASE|connection\s*failed|sql\s*error",
                "description": "Database-related issues",
                "severity": ErrorSeverity.CRITICAL,
                "category": "database"
            },
            
            # Network patterns
            {
                "pattern": r"network|Network|NETWORK|connection\s*refused|dns\s*error",
                "description": "Network connectivity issues",
                "severity": ErrorSeverity.HIGH,
                "category": "network"
            }
        ]
    
    async def analyze_logs(self, log_entries: List[str], time_window: Optional[timedelta] = None) -> LogAnalysisResult:
        """Analyze log entries and detect patterns and anomalies."""
        if not log_entries:
            return LogAnalysisResult(
                total_entries=0,
                error_entries=0,
                warning_entries=0,
                info_entries=0,
                patterns_detected=[],
                anomalies=[],
                recommendations=[],
                analysis_time=datetime.utcnow()
            )
        
        # Parse log entries
        parsed_entries = await self._parse_log_entries(log_entries)
        
        # Filter by time window if specified
        if time_window:
            cutoff_time = datetime.utcnow() - time_window
            parsed_entries = [
                entry for entry in parsed_entries
                if entry.get("timestamp", datetime.utcnow()) >= cutoff_time
            ]
        
        # Categorize entries by level
        error_entries = [e for e in parsed_entries if e.get("level", "").lower() in ["error", "fatal", "critical"]]
        warning_entries = [e for e in parsed_entries if e.get("level", "").lower() in ["warn", "warning"]]
        info_entries = [e for e in parsed_entries if e.get("level", "").lower() in ["info", "debug", "trace"]]
        
        # Detect patterns
        patterns_detected = await self._detect_patterns(parsed_entries)
        
        # Detect anomalies
        anomalies = await self._detect_anomalies(parsed_entries)
        
        # Generate recommendations
        recommendations = await self._generate_recommendations(patterns_detected, anomalies, parsed_entries)
        
        return LogAnalysisResult(
            total_entries=len(parsed_entries),
            error_entries=len(error_entries),
            warning_entries=len(warning_entries),
            info_entries=len(info_entries),
            patterns_detected=patterns_detected,
            anomalies=anomalies,
            recommendations=recommendations,
            analysis_time=datetime.utcnow()
        )
    
    async def _parse_log_entries(self, log_entries: List[str]) -> List[Dict[str, Any]]:
        """Parse raw log entries into structured data."""
        parsed_entries = []
        
        for i, entry in enumerate(log_entries):
            parsed_entry = {
                "raw": entry,
                "index": i,
                "timestamp": datetime.utcnow(),  # Default timestamp
                "level": "info",  # Default level
                "message": entry,
                "component": "unknown"
            }
            
            # Try to extract timestamp
            timestamp_match = re.search(
                r"(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)",
                entry
            )
            if timestamp_match:
                try:
                    timestamp_str = timestamp_match.group(1)
                    # Handle different timestamp formats
                    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"]:
                        try:
                            parsed_entry["timestamp"] = datetime.strptime(timestamp_str.split('.')[0], fmt)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
            
            # Try to extract log level
            level_match = re.search(r"\b(DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\b", entry, re.IGNORECASE)
            if level_match:
                parsed_entry["level"] = level_match.group(1).lower()
            
            # Try to extract component/logger name
            component_match = re.search(r"\[([^\]]+)\]|\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)\b", entry)
            if component_match:
                parsed_entry["component"] = component_match.group(1) or component_match.group(2)
            
            # Extract the actual message (remove timestamp, level, component)
            message = entry
            if timestamp_match:
                message = message.replace(timestamp_match.group(0), "").strip()
            if level_match:
                message = message.replace(level_match.group(0), "").strip()
            if component_match:
                message = message.replace(component_match.group(0), "").strip()
            
            parsed_entry["message"] = message.strip("- :[]")
            
            parsed_entries.append(parsed_entry)
        
        return parsed_entries
    
    async def _detect_patterns(self, parsed_entries: List[Dict[str, Any]]) -> List[LogPattern]:
        """Detect known patterns in log entries."""
        pattern_matches = defaultdict(list)
        
        # Check each entry against known patterns
        for entry in parsed_entries:
            message = entry.get("message", "")
            raw = entry.get("raw", "")
            
            for pattern_def in self._known_patterns:
                pattern = pattern_def["pattern"]
                if re.search(pattern, message, re.IGNORECASE) or re.search(pattern, raw, re.IGNORECASE):
                    pattern_matches[pattern].append({
                        "entry": entry,
                        "pattern_def": pattern_def
                    })
        
        # Convert matches to LogPattern objects
        detected_patterns = []
        for pattern, matches in pattern_matches.items():
            if not matches:
                continue
            
            pattern_def = matches[0]["pattern_def"]
            entries = [match["entry"] for match in matches]
            
            # Get timestamps
            timestamps = [entry.get("timestamp", datetime.utcnow()) for entry in entries]
            first_seen = min(timestamps)
            last_seen = max(timestamps)
            
            # Get examples (up to 5)
            examples = [entry.get("raw", entry.get("message", ""))[:200] for entry in entries[:5]]
            
            log_pattern = LogPattern(
                pattern=pattern,
                description=pattern_def["description"],
                severity=pattern_def["severity"],
                frequency=len(matches),
                first_seen=first_seen,
                last_seen=last_seen,
                examples=examples
            )
            
            detected_patterns.append(log_pattern)
        
        # Sort by frequency (most frequent first)
        detected_patterns.sort(key=lambda p: p.frequency, reverse=True)
        
        return detected_patterns
    
    async def _detect_anomalies(self, parsed_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect anomalies in log patterns."""
        anomalies = []
        
        if len(parsed_entries) < 10:  # Need sufficient data for anomaly detection
            return anomalies
        
        # Time-based anomaly detection
        time_anomalies = await self._detect_time_anomalies(parsed_entries)
        anomalies.extend(time_anomalies)
        
        # Frequency-based anomaly detection
        frequency_anomalies = await self._detect_frequency_anomalies(parsed_entries)
        anomalies.extend(frequency_anomalies)
        
        # Content-based anomaly detection
        content_anomalies = await self._detect_content_anomalies(parsed_entries)
        anomalies.extend(content_anomalies)
        
        return anomalies
    
    async def _detect_time_anomalies(self, parsed_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect time-based anomalies (unusual timing patterns)."""
        anomalies = []
        
        # Group entries by hour
        hourly_counts = defaultdict(int)
        for entry in parsed_entries:
            timestamp = entry.get("timestamp", datetime.utcnow())
            hour = timestamp.hour
            hourly_counts[hour] += 1
        
        if len(hourly_counts) < 3:  # Need at least 3 hours of data
            return anomalies
        
        # Calculate average and detect outliers
        counts = list(hourly_counts.values())
        avg_count = sum(counts) / len(counts)
        std_dev = (sum((x - avg_count) ** 2 for x in counts) / len(counts)) ** 0.5
        
        # Detect hours with unusually high activity
        for hour, count in hourly_counts.items():
            if count > avg_count + 2 * std_dev:  # More than 2 standard deviations
                anomalies.append({
                    "type": "time_anomaly",
                    "description": f"Unusually high log activity at hour {hour}",
                    "severity": ErrorSeverity.MEDIUM,
                    "details": {
                        "hour": hour,
                        "count": count,
                        "average": avg_count,
                        "threshold": avg_count + 2 * std_dev
                    }
                })
        
        return anomalies
    
    async def _detect_frequency_anomalies(self, parsed_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect frequency-based anomalies (unusual message frequencies)."""
        anomalies = []
        
        # Count message patterns
        message_counts = Counter()
        for entry in parsed_entries:
            # Normalize message for pattern detection
            message = entry.get("message", "")
            # Remove numbers and specific values to find patterns
            normalized = re.sub(r'\d+', 'N', message)
            normalized = re.sub(r'[a-f0-9]{8,}', 'HASH', normalized)  # Remove hashes/IDs
            message_counts[normalized] += 1
        
        total_messages = len(parsed_entries)
        
        # Detect messages that appear unusually frequently
        for message, count in message_counts.most_common(10):
            frequency = count / total_messages
            if frequency > 0.1 and count > 5:  # More than 10% of all messages and at least 5 occurrences
                anomalies.append({
                    "type": "frequency_anomaly",
                    "description": f"Message pattern appears unusually frequently",
                    "severity": ErrorSeverity.MEDIUM,
                    "details": {
                        "pattern": message[:100],
                        "count": count,
                        "frequency": frequency,
                        "total_messages": total_messages
                    }
                })
        
        return anomalies
    
    async def _detect_content_anomalies(self, parsed_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect content-based anomalies (unusual message content)."""
        anomalies = []
        
        # Detect sudden appearance of new error types
        error_entries = [e for e in parsed_entries if e.get("level", "").lower() in ["error", "fatal", "critical"]]
        
        if len(error_entries) > 5:
            # Group errors by time windows
            time_windows = defaultdict(list)
            for entry in error_entries:
                timestamp = entry.get("timestamp", datetime.utcnow())
                # Group by 10-minute windows
                window = timestamp.replace(minute=(timestamp.minute // 10) * 10, second=0, microsecond=0)
                time_windows[window].append(entry)
            
            # Detect windows with unusually many different error types
            for window, entries in time_windows.items():
                if len(entries) < 3:
                    continue
                
                unique_messages = set(entry.get("message", "")[:50] for entry in entries)
                if len(unique_messages) >= len(entries) * 0.8:  # 80% unique messages
                    anomalies.append({
                        "type": "content_anomaly",
                        "description": f"High diversity of error messages in short time window",
                        "severity": ErrorSeverity.HIGH,
                        "details": {
                            "time_window": window.isoformat(),
                            "total_errors": len(entries),
                            "unique_messages": len(unique_messages),
                            "diversity_ratio": len(unique_messages) / len(entries)
                        }
                    })
        
        return anomalies
    
    async def _generate_recommendations(self, patterns: List[LogPattern], anomalies: List[Dict[str, Any]], entries: List[Dict[str, Any]]) -> List[str]:
        """Generate recommendations based on detected patterns and anomalies."""
        recommendations = []
        
        # Pattern-based recommendations
        critical_patterns = [p for p in patterns if p.severity == ErrorSeverity.CRITICAL]
        if critical_patterns:
            recommendations.append(f"Found {len(critical_patterns)} critical error patterns. Immediate investigation required.")
        
        high_frequency_patterns = [p for p in patterns if p.frequency > 10]
        if high_frequency_patterns:
            recommendations.append(f"Found {len(high_frequency_patterns)} high-frequency error patterns. Consider implementing fixes or monitoring.")
        
        # Anomaly-based recommendations
        time_anomalies = [a for a in anomalies if a["type"] == "time_anomaly"]
        if time_anomalies:
            recommendations.append("Detected unusual timing patterns in logs. Check for scheduled jobs or traffic spikes.")
        
        frequency_anomalies = [a for a in anomalies if a["type"] == "frequency_anomaly"]
        if frequency_anomalies:
            recommendations.append("Detected repetitive error messages. Consider implementing error deduplication or fixing root causes.")
        
        content_anomalies = [a for a in anomalies if a["type"] == "content_anomaly"]
        if content_anomalies:
            recommendations.append("Detected diverse error patterns in short time windows. May indicate system instability.")
        
        # General recommendations based on log volume and error rate
        error_entries = [e for e in entries if e.get("level", "").lower() in ["error", "fatal", "critical"]]
        error_rate = len(error_entries) / len(entries) if entries else 0
        
        if error_rate > 0.1:  # More than 10% errors
            recommendations.append(f"High error rate detected ({error_rate:.1%}). System health may be compromised.")
        elif error_rate > 0.05:  # More than 5% errors
            recommendations.append(f"Elevated error rate detected ({error_rate:.1%}). Monitor closely.")
        
        if not recommendations:
            recommendations.append("Log patterns appear normal. Continue regular monitoring.")
        
        return recommendations
    
    async def create_error_events_from_logs(self, log_entries: List[str], url: str) -> List[ErrorEvent]:
        """Convert log entries to ErrorEvent objects for integration with error tracking."""
        parsed_entries = await self._parse_log_entries(log_entries)
        error_events = []
        
        for entry in parsed_entries:
            level = entry.get("level", "").lower()
            if level in ["error", "fatal", "critical", "warn", "warning"]:
                # Determine severity
                if level in ["fatal", "critical"]:
                    severity = ErrorSeverity.CRITICAL
                elif level == "error":
                    severity = ErrorSeverity.HIGH
                elif level in ["warn", "warning"]:
                    severity = ErrorSeverity.MEDIUM
                else:
                    severity = ErrorSeverity.LOW
                
                # Create error event
                error_event = ErrorEvent(
                    id=f"{url}_log_{entry['index']}_{entry['timestamp'].isoformat()}",
                    url=url,
                    error_type=f"log_{level}",
                    message=entry.get("message", "")[:500],  # Limit message length
                    timestamp=entry.get("timestamp", datetime.utcnow()),
                    severity=severity,
                    metadata={
                        "component": entry.get("component", "unknown"),
                        "raw_log": entry.get("raw", "")[:1000],  # Limit raw log length
                        "log_level": level
                    }
                )
                
                error_events.append(error_event)
        
        return error_events