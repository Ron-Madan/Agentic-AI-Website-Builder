"""Core interfaces and abstract base classes for the agentic web app builder."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta


class TaskStatus(Enum):
    """Status of a task in the system."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(Enum):
    """Types of tasks that can be executed."""
    CODE_GENERATION = "code_generation"
    REPOSITORY_SETUP = "repository_setup"
    DEPLOYMENT = "deployment"
    TESTING = "testing"
    MONITORING = "monitoring"
    MONITORING_SETUP = "monitoring_setup"
    USER_APPROVAL = "user_approval"


class Phase(Enum):
    """Phases of project development."""
    PLANNING = "planning"
    DEVELOPMENT = "development"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    MONITORING = "monitoring"
    COMPLETED = "completed"


class EventType(Enum):
    """Types of events in the system."""
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    DEPLOYMENT_READY = "deployment_ready"
    TESTS_COMPLETED = "tests_completed"
    ERROR_DETECTED = "error_detected"
    USER_INTERVENTION_REQUIRED = "user_intervention_required"


@dataclass
class Task:
    """Represents a task in the system."""
    id: str
    type: TaskType
    description: str
    dependencies: List[str]
    estimated_duration: timedelta
    status: TaskStatus
    agent_assigned: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class AgentEvent:
    """Represents an event in the agent system."""
    event_id: str
    source_agent: str
    event_type: EventType
    payload: Dict[str, Any]
    timestamp: datetime


@dataclass
class ProjectRequest:
    """Represents a user request for a project."""
    user_id: str
    description: str
    requirements: List[str]
    preferences: Dict[str, Any]
    timestamp: datetime


class BaseAgent(ABC):
    """Abstract base class for all agents in the system."""
    
    def __init__(self, agent_id: str, state_manager: 'StateManager'):
        self.agent_id = agent_id
        self.state_manager = state_manager
    
    @abstractmethod
    async def execute_task(self, task: Task) -> Dict[str, Any]:
        """Execute a task and return the result."""
        pass
    
    @abstractmethod
    async def handle_event(self, event: AgentEvent) -> None:
        """Handle an incoming event."""
        pass
    
    async def publish_event(self, event_type: EventType, payload: Dict[str, Any]) -> None:
        """Publish an event to the system."""
        event = AgentEvent(
            event_id=f"{self.agent_id}_{datetime.now().isoformat()}",
            source_agent=self.agent_id,
            event_type=event_type,
            payload=payload,
            timestamp=datetime.now()
        )
        await self.state_manager.publish_event(event)


class StateManager(ABC):
    """Abstract interface for state management."""
    
    @abstractmethod
    async def store_project_state(self, project_id: str, state: Dict[str, Any]) -> None:
        """Store project state."""
        pass
    
    @abstractmethod
    async def get_project_state(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve project state."""
        pass
    
    @abstractmethod
    async def publish_event(self, event: AgentEvent) -> None:
        """Publish an event to the message queue."""
        pass
    
    @abstractmethod
    async def subscribe_to_events(self, agent_id: str, event_types: List[EventType]) -> None:
        """Subscribe an agent to specific event types."""
        pass
    
    @abstractmethod
    async def create_checkpoint(self, project_id: str) -> str:
        """Create a checkpoint for the project state."""
        pass
    
    @abstractmethod
    async def restore_from_checkpoint(self, checkpoint_id: str) -> Dict[str, Any]:
        """Restore project state from a checkpoint."""
        pass


class ToolInterface(ABC):
    """Abstract interface for tool integrations."""
    
    @abstractmethod
    async def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool command with parameters."""
        pass
    
    @abstractmethod
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """Validate tool parameters."""
        pass


class ErrorHandler(ABC):
    """Abstract interface for error handling."""
    
    @abstractmethod
    async def handle_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle an error and return recovery actions."""
        pass
    
    @abstractmethod
    async def create_checkpoint(self, project_id: str) -> str:
        """Create a checkpoint before risky operations."""
        pass
    
    @abstractmethod
    async def restore_from_checkpoint(self, project_id: str, checkpoint_id: str) -> None:
        """Restore from a checkpoint after failure."""
        pass