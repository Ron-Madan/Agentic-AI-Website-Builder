"""State Manager implementation with database integration."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import (
    AgentEvent,
    EventFilter,
    EventSubscription,
    ProjectRequest,
    ProjectState,
    Task,
)
from .database import (
    AgentEventDB,
    CheckpointDB,
    EventSubscriptionDB,
    ProjectRequestDB,
    ProjectStateDB,
    SessionLocal,
    TaskDB,
)

logger = logging.getLogger(__name__)


class StateManager:
    """Centralized state management with database persistence."""
    
    def __init__(self):
        """Initialize the state manager."""
        self.session_factory = SessionLocal
    
    def _get_session(self) -> Session:
        """Get a database session."""
        return self.session_factory()
    
    # Project State Management
    
    async def store_project_state(self, project_state: ProjectState) -> None:
        """Store project state in the database."""
        session = self._get_session()
        try:
            # Store or update project request
            request_db = session.query(ProjectRequestDB).filter_by(
                id=project_state.request.id
            ).first()
            
            if not request_db:
                request_db = ProjectRequestDB(
                    id=project_state.request.id,
                    user_id=project_state.request.user_id,
                    description=project_state.request.description,
                    requirements=project_state.request.requirements,
                    preferences=project_state.request.preferences,
                    created_at=project_state.request.created_at,
                    updated_at=project_state.request.updated_at,
                )
                session.add(request_db)
            else:
                request_db.description = project_state.request.description
                request_db.requirements = project_state.request.requirements
                request_db.preferences = project_state.request.preferences
                request_db.updated_at = project_state.request.updated_at
            
            # Store or update project state
            state_db = session.query(ProjectStateDB).filter_by(
                project_id=project_state.project_id
            ).first()
            
            if not state_db:
                state_db = ProjectStateDB(
                    id=project_state.id,
                    project_id=project_state.project_id,
                    current_phase=project_state.current_phase.value if hasattr(project_state.current_phase, 'value') else project_state.current_phase,
                    generated_files=[file.dict() for file in project_state.generated_files],
                    deployment_info=project_state.deployment_info.dict() if project_state.deployment_info else None,
                    monitoring_config=project_state.monitoring_config.dict() if project_state.monitoring_config else None,
                    checkpoints=project_state.checkpoints,
                    project_metadata=project_state.metadata,
                    created_at=project_state.created_at,
                    updated_at=project_state.updated_at,
                )
                session.add(state_db)
            else:
                state_db.current_phase = project_state.current_phase.value if hasattr(project_state.current_phase, 'value') else project_state.current_phase
                state_db.generated_files = [file.dict() for file in project_state.generated_files]
                state_db.deployment_info = project_state.deployment_info.dict() if project_state.deployment_info else None
                state_db.monitoring_config = project_state.monitoring_config.dict() if project_state.monitoring_config else None
                state_db.checkpoints = project_state.checkpoints
                state_db.project_metadata = project_state.metadata
                state_db.updated_at = project_state.updated_at
            
            # Store all tasks
            await self._store_tasks(session, project_state.get_all_tasks())
            
            session.commit()
            logger.info(f"Stored project state for project {project_state.project_id}")
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to store project state: {e}")
            raise
        finally:
            session.close()
    
    async def get_project_state(self, project_id: str) -> Optional[ProjectState]:
        """Retrieve project state from the database."""
        session = self._get_session()
        try:
            # Get project state
            state_db = session.query(ProjectStateDB).filter_by(
                project_id=project_id
            ).first()
            
            if not state_db:
                return None
            
            # Find the project request by looking through all requests for this project
            # In a real implementation, we'd have a proper foreign key relationship
            request_db = None
            all_requests = session.query(ProjectRequestDB).all()
            for req in all_requests:
                # Check if this request belongs to our project (simple heuristic)
                if req.user_id and req.description:  # Basic validation
                    request_db = req
                    break
            
            if not request_db:
                # Create a minimal request if none found
                request_db = ProjectRequestDB(
                    id=str(uuid4()),
                    user_id="unknown",
                    description="Recovered project",
                    requirements=[],
                    preferences={},
                    created_at=state_db.created_at,
                    updated_at=state_db.updated_at,
                )
            
            if not request_db:
                logger.error(f"Project request not found for project {project_id}")
                return None
            
            # Convert to Pydantic models
            request = ProjectRequest(
                id=request_db.id,
                user_id=request_db.user_id,
                description=request_db.description,
                requirements=request_db.requirements,
                preferences=request_db.preferences,
                created_at=request_db.created_at,
                updated_at=request_db.updated_at,
            )
            
            # Get all tasks for the project
            tasks = await self._get_tasks_by_project(session, project_id)
            
            # Separate tasks by status
            completed_tasks = [t for t in tasks if t.status.value == "completed"]
            pending_tasks = [t for t in tasks if t.status.value in ["pending", "in_progress", "waiting_for_approval"]]
            failed_tasks = [t for t in tasks if t.status.value == "failed"]
            
            project_state = ProjectState(
                id=state_db.id,
                project_id=state_db.project_id,
                request=request,
                current_phase=state_db.current_phase,
                completed_tasks=completed_tasks,
                pending_tasks=pending_tasks,
                failed_tasks=failed_tasks,
                generated_files=state_db.generated_files,
                deployment_info=state_db.deployment_info,
                monitoring_config=state_db.monitoring_config,
                checkpoints=state_db.checkpoints,
                metadata=state_db.project_metadata,
                created_at=state_db.created_at,
                updated_at=state_db.updated_at,
            )
            
            logger.info(f"Retrieved project state for project {project_id}")
            return project_state
            
        except SQLAlchemyError as e:
            logger.error(f"Failed to retrieve project state: {e}")
            raise
        finally:
            session.close()
    
    async def _store_tasks(self, session: Session, tasks: List[Task]) -> None:
        """Store tasks in the database."""
        for task in tasks:
            task_db = session.query(TaskDB).filter_by(id=task.id).first()
            
            if not task_db:
                task_db = TaskDB(
                    id=task.id,
                    project_id=task.project_id,
                    type=task.type.value if hasattr(task.type, 'value') else task.type,
                    description=task.description,
                    dependencies=task.dependencies,
                    estimated_duration_seconds=int(task.estimated_duration.total_seconds()) if task.estimated_duration else None,
                    actual_duration_seconds=int(task.actual_duration.total_seconds()) if task.actual_duration else None,
                    status=task.status.value if hasattr(task.status, 'value') else task.status,
                    agent_assigned=task.agent_assigned,
                    result=task.result,
                    error_message=task.error_message,
                    retry_count=task.retry_count,
                    max_retries=task.max_retries,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                )
                session.add(task_db)
            else:
                task_db.type = task.type.value if hasattr(task.type, 'value') else task.type
                task_db.description = task.description
                task_db.dependencies = task.dependencies
                task_db.estimated_duration_seconds = int(task.estimated_duration.total_seconds()) if task.estimated_duration else None
                task_db.actual_duration_seconds = int(task.actual_duration.total_seconds()) if task.actual_duration else None
                task_db.status = task.status.value if hasattr(task.status, 'value') else task.status
                task_db.agent_assigned = task.agent_assigned
                task_db.result = task.result
                task_db.error_message = task.error_message
                task_db.retry_count = task.retry_count
                task_db.max_retries = task.max_retries
                task_db.updated_at = task.updated_at
    
    async def _get_tasks_by_project(self, session: Session, project_id: str) -> List[Task]:
        """Get all tasks for a project."""
        tasks_db = session.query(TaskDB).filter_by(project_id=project_id).all()
        
        tasks = []
        for task_db in tasks_db:
            task = Task(
                id=task_db.id,
                project_id=task_db.project_id,
                type=task_db.type,
                description=task_db.description,
                dependencies=task_db.dependencies,
                estimated_duration=timedelta(seconds=task_db.estimated_duration_seconds) if task_db.estimated_duration_seconds else None,
                actual_duration=timedelta(seconds=task_db.actual_duration_seconds) if task_db.actual_duration_seconds else None,
                status=task_db.status,
                agent_assigned=task_db.agent_assigned,
                result=task_db.result,
                error_message=task_db.error_message,
                retry_count=task_db.retry_count,
                max_retries=task_db.max_retries,
                created_at=task_db.created_at,
                updated_at=task_db.updated_at,
            )
            tasks.append(task)
        
        return tasks
    
    # Event Management
    
    async def publish_event(self, event: AgentEvent) -> None:
        """Publish an event to the database."""
        session = self._get_session()
        try:
            event_db = AgentEventDB(
                id=event.id,
                event_id=event.event_id,
                source_agent=event.source_agent,
                target_agents=event.target_agents,
                event_type=event.event_type.value if hasattr(event.event_type, 'value') else event.event_type,
                payload=event.payload,
                project_id=event.project_id,
                task_id=event.task_id,
                priority=event.priority,
                expires_at=event.expires_at,
                processed=event.processed,
                processing_results=event.processing_results,
                created_at=event.created_at,
                updated_at=event.updated_at,
            )
            
            session.add(event_db)
            session.commit()
            
            logger.info(f"Published event {event.event_id} from {event.source_agent}")
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to publish event: {e}")
            raise
        finally:
            session.close()
    
    async def subscribe_to_events(self, subscription: EventSubscription) -> None:
        """Create an event subscription."""
        session = self._get_session()
        try:
            subscription_db = EventSubscriptionDB(
                id=subscription.id,
                subscriber_id=subscription.subscriber_id,
                subscription_name=subscription.subscription_name,
                filter_criteria=subscription.filter_criteria.dict(),
                active=subscription.active,
                callback_url=subscription.callback_url,
                delivery_mode=subscription.delivery_mode,
                max_queue_size=subscription.max_queue_size,
                retry_policy=subscription.retry_policy,
                created_at=subscription.created_at,
                updated_at=subscription.updated_at,
            )
            
            session.add(subscription_db)
            session.commit()
            
            logger.info(f"Created subscription {subscription.subscription_name} for {subscription.subscriber_id}")
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to create subscription: {e}")
            raise
        finally:
            session.close()
    
    async def get_events_for_subscriber(self, subscriber_id: str, limit: int = 100) -> List[AgentEvent]:
        """Get unprocessed events for a subscriber."""
        session = self._get_session()
        try:
            # Get active subscriptions for the subscriber
            subscriptions = session.query(EventSubscriptionDB).filter_by(
                subscriber_id=subscriber_id,
                active=True
            ).all()
            
            if not subscriptions:
                return []
            
            # Get unprocessed events that match any subscription
            events = []
            for subscription in subscriptions:
                filter_criteria = EventFilter(**subscription.filter_criteria)
                
                query = session.query(AgentEventDB).filter_by(processed=False)
                
                # Apply filters
                if filter_criteria.event_types:
                    query = query.filter(AgentEventDB.event_type.in_([et.value for et in filter_criteria.event_types]))
                
                if filter_criteria.source_agents:
                    query = query.filter(AgentEventDB.source_agent.in_(filter_criteria.source_agents))
                
                if filter_criteria.project_ids:
                    query = query.filter(AgentEventDB.project_id.in_(filter_criteria.project_ids))
                
                if filter_criteria.min_priority:
                    query = query.filter(AgentEventDB.priority >= filter_criteria.min_priority)
                
                if filter_criteria.max_priority:
                    query = query.filter(AgentEventDB.priority <= filter_criteria.max_priority)
                
                # Check if event is targeted to this subscriber or is a broadcast
                query = query.filter(
                    (AgentEventDB.target_agents.is_(None)) |
                    (AgentEventDB.target_agents.contains(subscriber_id))
                )
                
                subscription_events = query.order_by(AgentEventDB.priority, AgentEventDB.created_at).limit(limit).all()
                
                for event_db in subscription_events:
                    event = AgentEvent(
                        id=event_db.id,
                        event_id=event_db.event_id,
                        source_agent=event_db.source_agent,
                        target_agents=event_db.target_agents,
                        event_type=event_db.event_type,
                        payload=event_db.payload,
                        project_id=event_db.project_id,
                        task_id=event_db.task_id,
                        priority=event_db.priority,
                        expires_at=event_db.expires_at,
                        processed=event_db.processed,
                        processing_results=event_db.processing_results,
                        created_at=event_db.created_at,
                        updated_at=event_db.updated_at,
                    )
                    events.append(event)
            
            return events[:limit]  # Limit total events returned
            
        except SQLAlchemyError as e:
            logger.error(f"Failed to get events for subscriber: {e}")
            raise
        finally:
            session.close()
    
    async def mark_event_processed(self, event_id: str, processing_result: Optional[Dict[str, Any]] = None) -> None:
        """Mark an event as processed."""
        session = self._get_session()
        try:
            event_db = session.query(AgentEventDB).filter_by(event_id=event_id).first()
            
            if event_db:
                event_db.processed = True
                if processing_result:
                    event_db.processing_results.update(processing_result)
                event_db.updated_at = datetime.utcnow()
                
                session.commit()
                logger.info(f"Marked event {event_id} as processed")
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to mark event as processed: {e}")
            raise
        finally:
            session.close()
    
    # Checkpoint Management
    
    async def create_checkpoint(self, project_id: str, checkpoint_name: Optional[str] = None) -> str:
        """Create a checkpoint for the project state."""
        session = self._get_session()
        try:
            # Get current project state
            project_state = await self.get_project_state(project_id)
            if not project_state:
                raise ValueError(f"Project {project_id} not found")
            
            # Create checkpoint
            checkpoint_id = str(uuid4())
            checkpoint_db = CheckpointDB(
                id=checkpoint_id,
                project_id=project_id,
                checkpoint_name=checkpoint_name or f"checkpoint_{datetime.utcnow().isoformat()}",
                state_snapshot=project_state.dict(),
                created_at=datetime.utcnow(),
            )
            
            session.add(checkpoint_db)
            
            # Update project state with new checkpoint
            project_state.checkpoints.append(checkpoint_id)
            await self.store_project_state(project_state)
            
            session.commit()
            
            logger.info(f"Created checkpoint {checkpoint_id} for project {project_id}")
            return checkpoint_id
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to create checkpoint: {e}")
            raise
        finally:
            session.close()
    
    async def restore_from_checkpoint(self, checkpoint_id: str) -> ProjectState:
        """Restore project state from a checkpoint."""
        session = self._get_session()
        try:
            checkpoint_db = session.query(CheckpointDB).filter_by(id=checkpoint_id).first()
            
            if not checkpoint_db:
                raise ValueError(f"Checkpoint {checkpoint_id} not found")
            
            # Restore project state from snapshot
            state_data = checkpoint_db.state_snapshot
            project_state = ProjectState(**state_data)
            
            # Store the restored state
            await self.store_project_state(project_state)
            
            logger.info(f"Restored project state from checkpoint {checkpoint_id}")
            return project_state
            
        except SQLAlchemyError as e:
            logger.error(f"Failed to restore from checkpoint: {e}")
            raise
        finally:
            session.close()
    
    async def restore_project_state(self, project_id: str, state_data: Any) -> bool:
        """Restore project state from provided state data (used by checkpoint system)."""
        try:
            # If state_data is already a ProjectState object, use it directly
            if isinstance(state_data, ProjectState):
                project_state = state_data
            elif isinstance(state_data, dict):
                # Try to reconstruct ProjectState from dict
                if "project_state" in state_data:
                    # Handle nested structure from checkpoint system
                    project_state = ProjectState(**state_data["project_state"])
                else:
                    # Direct state data
                    project_state = ProjectState(**state_data)
            else:
                logger.error(f"Invalid state data type for project {project_id}: {type(state_data)}")
                return False
            
            # Ensure project_id matches
            if project_state.project_id != project_id:
                logger.warning(f"Project ID mismatch: expected {project_id}, got {project_state.project_id}")
                project_state.project_id = project_id
            
            # Store the restored state
            await self.store_project_state(project_state)
            
            logger.info(f"Successfully restored project state for project {project_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore project state for {project_id}: {str(e)}")
            return False
    
    async def get_checkpoints(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all checkpoints for a project."""
        session = self._get_session()
        try:
            checkpoints_db = session.query(CheckpointDB).filter_by(
                project_id=project_id
            ).order_by(CheckpointDB.created_at.desc()).all()
            
            checkpoints = []
            for checkpoint_db in checkpoints_db:
                checkpoints.append({
                    "id": checkpoint_db.id,
                    "project_id": checkpoint_db.project_id,
                    "checkpoint_name": checkpoint_db.checkpoint_name,
                    "created_at": checkpoint_db.created_at,
                })
            
            return checkpoints
            
        except SQLAlchemyError as e:
            logger.error(f"Failed to get checkpoints: {e}")
            raise
        finally:
            session.close()
    
    # Utility Methods
    
    async def cleanup_expired_events(self) -> int:
        """Clean up expired events from the database."""
        session = self._get_session()
        try:
            now = datetime.utcnow()
            expired_events = session.query(AgentEventDB).filter(
                AgentEventDB.expires_at.isnot(None),
                AgentEventDB.expires_at < now
            ).all()
            
            count = len(expired_events)
            for event in expired_events:
                session.delete(event)
            
            session.commit()
            
            if count > 0:
                logger.info(f"Cleaned up {count} expired events")
            
            return count
            
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Failed to cleanup expired events: {e}")
            raise
        finally:
            session.close()
    
    async def get_project_statistics(self, project_id: str) -> Dict[str, Any]:
        """Get statistics for a project."""
        session = self._get_session()
        try:
            # Get task counts by status
            task_stats = session.query(TaskDB.status, session.query(TaskDB).filter_by(project_id=project_id).count()).filter_by(project_id=project_id).group_by(TaskDB.status).all()
            
            # Get event counts
            event_count = session.query(AgentEventDB).filter_by(project_id=project_id).count()
            
            # Get checkpoint count
            checkpoint_count = session.query(CheckpointDB).filter_by(project_id=project_id).count()
            
            stats = {
                "project_id": project_id,
                "task_counts": dict(task_stats),
                "total_events": event_count,
                "total_checkpoints": checkpoint_count,
            }
            
            return stats
            
        except SQLAlchemyError as e:
            logger.error(f"Failed to get project statistics: {e}")
            raise
        finally:
            session.close()

class InMemoryStateManager:
    """Simple in-memory state manager for development/testing."""
    
    def __init__(self):
        self.projects = {}
        self.events = []
        self.subscriptions = {}
        self.checkpoints = {}
    
    async def store_project_state(self, project_id: str, state: Dict[str, Any]) -> None:
        """Store project state in memory."""
        self.projects[project_id] = state
    
    async def get_project_state(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve project state from memory."""
        return self.projects.get(project_id)
    
    async def publish_event(self, event) -> None:
        """Publish an event to memory."""
        self.events.append(event)
    
    async def subscribe_to_events(self, agent_id: str, event_types: List[str]) -> None:
        """Subscribe an agent to specific event types."""
        self.subscriptions[agent_id] = event_types
    
    async def create_checkpoint(self, project_id: str) -> str:
        """Create a checkpoint for the project state."""
        checkpoint_id = str(uuid4())
        if project_id in self.projects:
            self.checkpoints[checkpoint_id] = self.projects[project_id].copy()
        return checkpoint_id
    
    async def restore_from_checkpoint(self, checkpoint_id: str) -> Dict[str, Any]:
        """Restore project state from a checkpoint."""
        return self.checkpoints.get(checkpoint_id, {})