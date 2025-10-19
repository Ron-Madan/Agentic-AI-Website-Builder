"""Governance models for human-in-the-loop workflows."""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator

from .base import BaseModelWithTimestamp


class InterventionType(str, Enum):
    """Types of user interventions."""
    
    APPROVAL_REQUEST = "approval_request"
    CRITICAL_ACTION_CONFIRMATION = "critical_action_confirmation"
    ERROR_RESOLUTION = "error_resolution"
    PLAN_MODIFICATION = "plan_modification"
    MANUAL_OVERRIDE = "manual_override"
    FEEDBACK_REQUEST = "feedback_request"


class InterventionStatus(str, Enum):
    """Status of intervention requests."""
    
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class InterventionPriority(str, Enum):
    """Priority levels for interventions."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FeedbackType(str, Enum):
    """Types of user feedback."""
    
    PREFERENCE = "preference"
    CORRECTION = "correction"
    GUIDANCE = "guidance"
    RATING = "rating"
    SUGGESTION = "suggestion"


class InterventionRequest(BaseModelWithTimestamp):
    """Model for user intervention requests."""
    
    project_id: str = Field(..., description="ID of the associated project")
    task_id: Optional[str] = Field(None, description="ID of the associated task")
    agent_id: str = Field(..., description="ID of the requesting agent")
    intervention_type: InterventionType = Field(..., description="Type of intervention requested")
    priority: InterventionPriority = Field(default=InterventionPriority.MEDIUM, description="Priority level")
    status: InterventionStatus = Field(default=InterventionStatus.PENDING, description="Current status")
    
    title: str = Field(..., description="Brief title of the intervention request")
    description: str = Field(..., description="Detailed description of what needs intervention")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context data")
    
    # Options and choices
    options: List[Dict[str, Any]] = Field(default_factory=list, description="Available options for user to choose from")
    default_option: Optional[str] = Field(None, description="Default option if no response")
    
    # Timing
    expires_at: Optional[datetime] = Field(None, description="When this request expires")
    responded_at: Optional[datetime] = Field(None, description="When user responded")
    
    # Response
    user_response: Optional[Dict[str, Any]] = Field(None, description="User's response data")
    response_reason: Optional[str] = Field(None, description="Reason provided by user")
    
    # Metadata
    requires_immediate_attention: bool = Field(default=False, description="Whether this requires immediate attention")
    can_proceed_without_response: bool = Field(default=False, description="Whether system can proceed without response")
    auto_approve_after: Optional[timedelta] = Field(None, description="Auto-approve after this duration")
    
    @validator('title')
    def title_not_empty(cls, v: str) -> str:
        """Validate that title is not empty."""
        if not v.strip():
            raise ValueError('Title cannot be empty')
        return v.strip()
    
    @validator('description')
    def description_not_empty(cls, v: str) -> str:
        """Validate that description is not empty."""
        if not v.strip():
            raise ValueError('Description cannot be empty')
        return v.strip()
    
    @validator('expires_at')
    def expires_at_future(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Validate that expiration time is in the future."""
        if v is not None and v <= datetime.utcnow():
            raise ValueError('Expiration time must be in the future')
        return v
    
    def is_expired(self) -> bool:
        """Check if the intervention request has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def should_auto_approve(self) -> bool:
        """Check if request should be auto-approved."""
        if not self.auto_approve_after or self.status != InterventionStatus.PENDING:
            return False
        return datetime.utcnow() > (self.created_at + self.auto_approve_after)
    
    def respond(self, approved: bool, response_data: Optional[Dict[str, Any]] = None, reason: Optional[str] = None) -> None:
        """Record user response to the intervention."""
        self.status = InterventionStatus.APPROVED if approved else InterventionStatus.REJECTED
        self.responded_at = datetime.utcnow()
        self.user_response = response_data or {}
        self.response_reason = reason
        self.update_timestamp()


class UserFeedback(BaseModelWithTimestamp):
    """Model for user feedback on agent actions."""
    
    project_id: str = Field(..., description="ID of the associated project")
    task_id: Optional[str] = Field(None, description="ID of the associated task")
    agent_id: str = Field(..., description="ID of the agent being given feedback")
    feedback_type: FeedbackType = Field(..., description="Type of feedback")
    
    # Feedback content
    subject: str = Field(..., description="Subject of the feedback")
    content: str = Field(..., description="Detailed feedback content")
    rating: Optional[int] = Field(None, description="Numeric rating (1-5)")
    tags: List[str] = Field(default_factory=list, description="Tags for categorizing feedback")
    
    # Context
    action_context: Dict[str, Any] = Field(default_factory=dict, description="Context of the action being reviewed")
    suggested_improvement: Optional[str] = Field(None, description="Suggested improvement")
    
    # Processing
    processed: bool = Field(default=False, description="Whether feedback has been processed")
    applied: bool = Field(default=False, description="Whether feedback has been applied")
    processing_notes: Optional[str] = Field(None, description="Notes from processing the feedback")
    
    @validator('subject')
    def subject_not_empty(cls, v: str) -> str:
        """Validate that subject is not empty."""
        if not v.strip():
            raise ValueError('Subject cannot be empty')
        return v.strip()
    
    @validator('content')
    def content_not_empty(cls, v: str) -> str:
        """Validate that content is not empty."""
        if not v.strip():
            raise ValueError('Content cannot be empty')
        return v.strip()
    
    @validator('rating')
    def rating_valid_range(cls, v: Optional[int]) -> Optional[int]:
        """Validate rating is within valid range."""
        if v is not None and not 1 <= v <= 5:
            raise ValueError('Rating must be between 1 and 5')
        return v
    
    def mark_processed(self, applied: bool = False, notes: Optional[str] = None) -> None:
        """Mark feedback as processed."""
        self.processed = True
        self.applied = applied
        self.processing_notes = notes
        self.update_timestamp()


class UserPreference(BaseModelWithTimestamp):
    """Model for learned user preferences."""
    
    user_id: str = Field(..., description="ID of the user")
    project_id: Optional[str] = Field(None, description="Project-specific preference (None for global)")
    agent_type: Optional[str] = Field(None, description="Agent type this preference applies to")
    
    # Preference details
    category: str = Field(..., description="Category of preference (e.g., 'deployment', 'testing', 'ui')")
    key: str = Field(..., description="Specific preference key")
    value: Union[str, int, float, bool, Dict[str, Any]] = Field(..., description="Preference value")
    
    # Learning metadata
    confidence: float = Field(default=0.5, description="Confidence in this preference (0.0-1.0)")
    source: str = Field(..., description="How this preference was learned")
    frequency: int = Field(default=1, description="How often this preference has been observed")
    last_reinforced: datetime = Field(default_factory=datetime.utcnow, description="When preference was last reinforced")
    
    @validator('confidence')
    def confidence_valid_range(cls, v: float) -> float:
        """Validate confidence is within valid range."""
        if not 0.0 <= v <= 1.0:
            raise ValueError('Confidence must be between 0.0 and 1.0')
        return v
    
    @validator('frequency')
    def frequency_positive(cls, v: int) -> int:
        """Validate frequency is positive."""
        if v <= 0:
            raise ValueError('Frequency must be positive')
        return v
    
    def reinforce(self, weight: float = 1.0) -> None:
        """Reinforce this preference, increasing confidence and frequency."""
        self.frequency += 1
        self.confidence = min(1.0, self.confidence + (weight * 0.1))
        self.last_reinforced = datetime.utcnow()
        self.update_timestamp()


class GovernancePolicy(BaseModelWithTimestamp):
    """Model for governance policies and rules."""
    
    name: str = Field(..., description="Name of the policy")
    description: str = Field(..., description="Description of what this policy governs")
    
    # Scope
    applies_to_agents: List[str] = Field(default_factory=list, description="Agent types this policy applies to")
    applies_to_actions: List[str] = Field(default_factory=list, description="Action types this policy applies to")
    applies_to_projects: List[str] = Field(default_factory=list, description="Project types this policy applies to")
    
    # Rules
    requires_approval: bool = Field(default=False, description="Whether actions require approval")
    approval_timeout: Optional[timedelta] = Field(None, description="Timeout for approval requests")
    auto_approve_conditions: List[Dict[str, Any]] = Field(default_factory=list, description="Conditions for auto-approval")
    
    # Escalation
    escalation_rules: List[Dict[str, Any]] = Field(default_factory=list, description="Rules for escalating to higher authority")
    notification_channels: List[str] = Field(default_factory=list, description="Channels to notify for this policy")
    
    # Status
    active: bool = Field(default=True, description="Whether this policy is active")
    priority: int = Field(default=5, description="Policy priority (1=highest, 10=lowest)")
    
    @validator('name')
    def name_not_empty(cls, v: str) -> str:
        """Validate that name is not empty."""
        if not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()
    
    @validator('priority')
    def priority_valid_range(cls, v: int) -> int:
        """Validate priority is within valid range."""
        if not 1 <= v <= 10:
            raise ValueError('Priority must be between 1 and 10')
        return v
    
    def applies_to(self, agent_type: str, action_type: str, project_type: Optional[str] = None) -> bool:
        """Check if this policy applies to the given context."""
        if not self.active:
            return False
        
        if self.applies_to_agents and agent_type not in self.applies_to_agents:
            return False
        
        if self.applies_to_actions and action_type not in self.applies_to_actions:
            return False
        
        if self.applies_to_projects and project_type and project_type not in self.applies_to_projects:
            return False
        
        return True


class InterventionDecision(BaseModel):
    """Model for intervention decision results."""
    
    request_id: str = Field(..., description="ID of the intervention request")
    decision: InterventionStatus = Field(..., description="The decision made")
    decision_data: Dict[str, Any] = Field(default_factory=dict, description="Additional decision data")
    reason: Optional[str] = Field(None, description="Reason for the decision")
    auto_decided: bool = Field(default=False, description="Whether decision was made automatically")
    decided_at: datetime = Field(default_factory=datetime.utcnow, description="When decision was made")