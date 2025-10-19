"""Base agent implementations."""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..core.interfaces import BaseAgent, Task, AgentEvent, EventType, TaskStatus
from ..core.config import get_settings


logger = logging.getLogger(__name__)


class AgentBase(BaseAgent):
    """Base implementation for all agents."""
    
    def __init__(self, agent_id: str, state_manager: 'StateManager'):
        super().__init__(agent_id, state_manager)
        self.settings = get_settings()
        self.logger = logging.getLogger(f"{__name__}.{agent_id}")
        self._event_handlers: Dict[EventType, List[callable]] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
    
    async def start(self) -> None:
        """Start the agent and subscribe to events."""
        self.logger.info(f"Starting agent {self.agent_id}")
        await self._subscribe_to_events()
    
    async def stop(self) -> None:
        """Stop the agent and cancel running tasks."""
        self.logger.info(f"Stopping agent {self.agent_id}")
        
        # Cancel all running tasks
        for task_id, task in self._running_tasks.items():
            if not task.done():
                task.cancel()
                self.logger.info(f"Cancelled task {task_id}")
        
        # Wait for tasks to complete
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)
    
    async def execute_task(self, task: Task) -> Dict[str, Any]:
        """Execute a task with error handling and logging."""
        self.logger.info(f"Executing task {task.id}: {task.description}")
        
        try:
            # Update task status to in progress
            await self._update_task_status(task.id, TaskStatus.IN_PROGRESS)
            
            # Execute the actual task
            result = await self._execute_task_impl(task)
            
            # Update task status to completed
            await self._update_task_status(task.id, TaskStatus.COMPLETED)
            
            # Publish completion event
            await self.publish_event(EventType.TASK_COMPLETED, {
                "task_id": task.id,
                "result": result
            })
            
            self.logger.info(f"Task {task.id} completed successfully")
            return result
            
        except Exception as e:
            self.logger.error(f"Task {task.id} failed: {str(e)}")
            
            # Update task status to failed
            await self._update_task_status(task.id, TaskStatus.FAILED)
            
            # Publish failure event
            await self.publish_event(EventType.TASK_FAILED, {
                "task_id": task.id,
                "error": str(e)
            })
            
            raise
    
    async def handle_event(self, event: AgentEvent) -> None:
        """Handle incoming events."""
        self.logger.debug(f"Received event {event.event_type} from {event.source_agent}")
        
        handlers = self._event_handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                self.logger.error(f"Error handling event {event.event_type}: {str(e)}")
    
    def register_event_handler(self, event_type: EventType, handler: callable) -> None:
        """Register an event handler for a specific event type."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    async def _execute_task_impl(self, task: Task) -> Dict[str, Any]:
        """Implement task execution logic in subclasses."""
        raise NotImplementedError("Subclasses must implement _execute_task_impl")
    
    async def _subscribe_to_events(self) -> None:
        """Subscribe to relevant events. Override in subclasses."""
        pass
    
    async def _update_task_status(self, task_id: str, status: TaskStatus) -> None:
        """Update task status in the state manager."""
        try:
            project_state = await self.state_manager.get_project_state(task_id.split("_")[0])
            if project_state:
                # Update task status in project state
                # This is a simplified implementation
                await self.state_manager.store_project_state(
                    task_id.split("_")[0], 
                    {**project_state, "last_updated": datetime.now().isoformat()}
                )
        except Exception as e:
            self.logger.error(f"Failed to update task status: {str(e)}")


class PlannerAgentBase(AgentBase):
    """Base class for Planner Agent."""
    
    def __init__(self, state_manager: 'StateManager'):
        super().__init__("planner", state_manager)
    
    async def _subscribe_to_events(self) -> None:
        """Subscribe to events relevant to planning."""
        await self.state_manager.subscribe_to_events(
            self.agent_id, 
            [EventType.USER_INTERVENTION_REQUIRED]
        )


class DeveloperAgentBase(AgentBase):
    """Base class for Developer Agent."""
    
    def __init__(self, state_manager: 'StateManager'):
        super().__init__("developer", state_manager)
    
    async def _subscribe_to_events(self) -> None:
        """Subscribe to events relevant to development."""
        await self.state_manager.subscribe_to_events(
            self.agent_id,
            [EventType.TASK_COMPLETED, EventType.DEPLOYMENT_READY]
        )


class TesterAgentBase(AgentBase):
    """Base class for Tester Agent."""
    
    def __init__(self, state_manager: 'StateManager'):
        super().__init__("tester", state_manager)
    
    async def _subscribe_to_events(self) -> None:
        """Subscribe to events relevant to testing."""
        await self.state_manager.subscribe_to_events(
            self.agent_id,
            [EventType.DEPLOYMENT_READY, EventType.TASK_COMPLETED]
        )


class MonitorAgentBase(AgentBase):
    """Base class for Monitor Agent."""
    
    def __init__(self, state_manager: 'StateManager'):
        super().__init__("monitor", state_manager)
    
    async def _subscribe_to_events(self) -> None:
        """Subscribe to events relevant to monitoring."""
        await self.state_manager.subscribe_to_events(
            self.agent_id,
            [EventType.TESTS_COMPLETED, EventType.ERROR_DETECTED]
        )