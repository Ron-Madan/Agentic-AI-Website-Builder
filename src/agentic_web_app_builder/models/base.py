"""Base models and enums for the agentic web app builder."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, validator


class TaskType(str, Enum):
    """Types of tasks that can be executed by agents."""
    
    CODE_GENERATION = "code_generation"
    REPOSITORY_SETUP = "repository_setup"
    DEPLOYMENT = "deployment"
    TESTING = "testing"
    MONITORING = "monitoring"
    MONITORING_SETUP = "monitoring_setup"
    ERROR_HANDLING = "error_handling"
    USER_INTERACTION = "user_interaction"


class TaskStatus(str, Enum):
    """Status of task execution."""
    
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_FOR_APPROVAL = "waiting_for_approval"


class Phase(str, Enum):
    """Project execution phases."""
    
    PLANNING = "planning"
    DEVELOPMENT = "development"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    MONITORING = "monitoring"
    COMPLETED = "completed"
    FAILED = "failed"


class DeploymentStatus(str, Enum):
    """Status of deployment operations."""
    
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class EventType(str, Enum):
    """Types of events in the agent communication system."""
    
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    DEPLOYMENT_READY = "deployment_ready"
    TESTS_COMPLETED = "tests_completed"
    ERROR_DETECTED = "error_detected"
    USER_INTERVENTION_REQUIRED = "user_intervention_required"
    PROJECT_STATE_UPDATED = "project_state_updated"
    CHECKPOINT_CREATED = "checkpoint_created"


class BaseModelWithTimestamp(BaseModel):
    """Base model with automatic timestamp fields."""
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        """Pydantic configuration."""
        
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        }
    
    def update_timestamp(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()