"""Event system models for agent communication."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

from .base import BaseModelWithTimestamp, EventType


class AgentEvent(BaseModelWithTimestamp):
    """Model for events in the agent communication system."""
    
    event_id: str = Field(..., description="Unique event identifier")
    source_agent: str = Field(..., description="ID of the agent that generated this event")
    target_agents: Optional[List[str]] = Field(None, description="List of target agent IDs (None for broadcast)")
    event_type: EventType = Field(..., description="Type of event")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event payload data")
    project_id: Optional[str] = Field(None, description="Associated project ID")
    task_id: Optional[str] = Field(None, description="Associated task ID")
    priority: int = Field(default=5, description="Event priority (1=highest, 10=lowest)")
    expires_at: Optional[datetime] = Field(None, description="Event expiration time")
    processed: bool = Field(default=False, description="Whether the event has been processed")
    processing_results: Dict[str, Any] = Field(default_factory=dict, description="Results from event processing")
    
    @validator('source_agent')
    def source_agent_not_empty(cls, v: str) -> str:
        """Validate that source_agent is not empty."""
        if not v.strip():
            raise ValueError('Source agent cannot be empty')
        return v.strip()
    
    @validator('priority')
    def priority_valid_range(cls, v: int) -> int:
        """Validate priority is within valid range."""
        if not 1 <= v <= 10:
            raise ValueError('Priority must be between 1 and 10')
        return v
    
    @validator('expires_at')
    def expires_at_future(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Validate that expiration time is in the future."""
        if v is not None and v <= datetime.utcnow():
            raise ValueError('Expiration time must be in the future')
        return v
    
    def is_expired(self) -> bool:
        """Check if the event has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def is_targeted_to(self, agent_id: str) -> bool:
        """Check if the event is targeted to a specific agent."""
        if self.target_agents is None:
            return True  # Broadcast event
        return agent_id in self.target_agents
    
    def mark_processed(self, processing_result: Optional[Dict[str, Any]] = None) -> None:
        """Mark the event as processed with optional result data."""
        self.processed = True
        if processing_result:
            self.processing_results.update(processing_result)
        self.update_timestamp()


class EventFilter(BaseModel):
    """Filter criteria for event subscriptions."""
    
    event_types: Optional[List[EventType]] = Field(None, description="List of event types to filter")
    source_agents: Optional[List[str]] = Field(None, description="List of source agents to filter")
    project_ids: Optional[List[str]] = Field(None, description="List of project IDs to filter")
    min_priority: Optional[int] = Field(None, description="Minimum priority level")
    max_priority: Optional[int] = Field(None, description="Maximum priority level")
    
    @validator('min_priority', 'max_priority')
    def priority_valid_range(cls, v: Optional[int]) -> Optional[int]:
        """Validate priority is within valid range."""
        if v is not None and not 1 <= v <= 10:
            raise ValueError('Priority must be between 1 and 10')
        return v
    
    def matches(self, event: AgentEvent) -> bool:
        """Check if an event matches this filter."""
        if self.event_types and event.event_type not in self.event_types:
            return False
        
        if self.source_agents and event.source_agent not in self.source_agents:
            return False
        
        if self.project_ids and event.project_id not in self.project_ids:
            return False
        
        if self.min_priority and event.priority < self.min_priority:
            return False
        
        if self.max_priority and event.priority > self.max_priority:
            return False
        
        return True


class EventSubscription(BaseModelWithTimestamp):
    """Model for agent event subscriptions."""
    
    subscriber_id: str = Field(..., description="ID of the subscribing agent")
    subscription_name: str = Field(..., description="Name of the subscription")
    filter_criteria: EventFilter = Field(..., description="Filter criteria for events")
    active: bool = Field(default=True, description="Whether the subscription is active")
    callback_url: Optional[str] = Field(None, description="Optional webhook URL for event delivery")
    delivery_mode: str = Field(default="queue", description="Event delivery mode (queue, webhook, both)")
    max_queue_size: int = Field(default=1000, description="Maximum number of queued events")
    retry_policy: Dict[str, Any] = Field(default_factory=dict, description="Retry policy for failed deliveries")
    
    @validator('subscriber_id')
    def subscriber_id_not_empty(cls, v: str) -> str:
        """Validate that subscriber_id is not empty."""
        if not v.strip():
            raise ValueError('Subscriber ID cannot be empty')
        return v.strip()
    
    @validator('delivery_mode')
    def delivery_mode_valid(cls, v: str) -> str:
        """Validate delivery mode."""
        valid_modes = ['queue', 'webhook', 'both']
        if v not in valid_modes:
            raise ValueError(f'Delivery mode must be one of: {valid_modes}')
        return v
    
    @validator('max_queue_size')
    def max_queue_size_positive(cls, v: int) -> int:
        """Validate max queue size is positive."""
        if v <= 0:
            raise ValueError('Max queue size must be positive')
        return v


class EventDeliveryStatus(BaseModel):
    """Status of event delivery to subscribers."""
    
    event_id: str = Field(..., description="ID of the event")
    subscriber_id: str = Field(..., description="ID of the subscriber")
    delivery_attempt: int = Field(default=1, description="Delivery attempt number")
    status: str = Field(..., description="Delivery status (pending, delivered, failed)")
    delivered_at: Optional[datetime] = Field(None, description="Timestamp of successful delivery")
    error_message: Optional[str] = Field(None, description="Error message for failed deliveries")
    next_retry_at: Optional[datetime] = Field(None, description="Timestamp for next retry attempt")
    
    @validator('status')
    def status_valid(cls, v: str) -> str:
        """Validate delivery status."""
        valid_statuses = ['pending', 'delivered', 'failed', 'expired']
        if v not in valid_statuses:
            raise ValueError(f'Status must be one of: {valid_statuses}')
        return v
    
    @validator('delivery_attempt')
    def delivery_attempt_positive(cls, v: int) -> int:
        """Validate delivery attempt is positive."""
        if v <= 0:
            raise ValueError('Delivery attempt must be positive')
        return v