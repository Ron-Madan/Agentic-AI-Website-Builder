"""User approval workflow for execution plans."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from ...models.project import ProjectRequest, Task as TaskModel
from ...core.interfaces import EventType


logger = logging.getLogger(__name__)


class ApprovalStatus(Enum):
    """Status of approval requests."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    EXPIRED = "expired"


class ApprovalType(Enum):
    """Types of approval requests."""
    EXECUTION_PLAN = "execution_plan"
    TASK_MODIFICATION = "task_modification"
    RESOURCE_ALLOCATION = "resource_allocation"
    DEPLOYMENT_APPROVAL = "deployment_approval"


@dataclass
class ApprovalRequest:
    """Represents a user approval request."""
    request_id: str
    project_id: str
    approval_type: ApprovalType
    title: str
    description: str
    data: Dict[str, Any]
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = None
    expires_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    response_data: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.expires_at is None:
            self.expires_at = self.created_at + timedelta(hours=24)  # Default 24-hour expiry
    
    def is_expired(self) -> bool:
        """Check if the approval request has expired."""
        return datetime.utcnow() > self.expires_at if self.expires_at else False
    
    def approve(self, response_data: Optional[Dict[str, Any]] = None) -> None:
        """Mark the request as approved."""
        self.status = ApprovalStatus.APPROVED
        self.responded_at = datetime.utcnow()
        self.response_data = response_data or {}
    
    def reject(self, reason: str) -> None:
        """Mark the request as rejected."""
        self.status = ApprovalStatus.REJECTED
        self.responded_at = datetime.utcnow()
        self.response_data = {"rejection_reason": reason}
    
    def modify(self, modifications: Dict[str, Any]) -> None:
        """Mark the request as modified."""
        self.status = ApprovalStatus.MODIFIED
        self.responded_at = datetime.utcnow()
        self.response_data = {"modifications": modifications}


@dataclass
class ExecutionPlanPresentation:
    """Formatted presentation of execution plan for user review."""
    project_summary: str
    total_tasks: int
    estimated_duration: str
    execution_strategy: str
    task_breakdown: List[Dict[str, Any]]
    resource_requirements: Dict[str, Any]
    risks_and_considerations: List[str]
    approval_options: List[str]


class ApprovalWorkflow:
    """Manages user approval workflows for execution plans."""
    
    def __init__(self, state_manager: 'StateManager'):
        self.state_manager = state_manager
        self.logger = logging.getLogger(__name__)
        self._pending_requests: Dict[str, ApprovalRequest] = {}
        self._approval_callbacks: Dict[str, Callable] = {}
    
    async def request_execution_plan_approval(
        self, 
        project_id: str, 
        execution_plan: Dict[str, Any],
        project_request: ProjectRequest
    ) -> ApprovalRequest:
        """Request user approval for an execution plan."""
        self.logger.info(f"Requesting execution plan approval for project {project_id}")
        
        try:
            # Create presentation of the execution plan
            presentation = self._create_execution_plan_presentation(execution_plan, project_request)
            
            # Create approval request
            request_id = f"approval_{project_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            
            approval_request = ApprovalRequest(
                request_id=request_id,
                project_id=project_id,
                approval_type=ApprovalType.EXECUTION_PLAN,
                title=f"Execution Plan Approval: {project_request.description[:50]}...",
                description="Please review and approve the execution plan for your web application project.",
                data={
                    "execution_plan": execution_plan,
                    "presentation": presentation.__dict__,
                    "project_request": project_request.dict()
                }
            )
            
            # Store the request
            self._pending_requests[request_id] = approval_request
            
            # Publish approval request event
            await self.state_manager.publish_event({
                "event_id": f"approval_request_{request_id}",
                "source_agent": "planner",
                "event_type": EventType.USER_INTERVENTION_REQUIRED,
                "payload": {
                    "approval_request_id": request_id,
                    "project_id": project_id,
                    "approval_type": approval_request.approval_type.value,
                    "title": approval_request.title,
                    "description": approval_request.description,
                    "presentation": presentation.__dict__,
                    "expires_at": approval_request.expires_at.isoformat()
                },
                "timestamp": datetime.utcnow()
            })
            
            self.logger.info(f"Execution plan approval requested: {request_id}")
            return approval_request
            
        except Exception as e:
            self.logger.error(f"Failed to request execution plan approval: {str(e)}")
            raise
    
    async def handle_approval_response(
        self, 
        request_id: str, 
        approved: bool, 
        modifications: Optional[Dict[str, Any]] = None,
        rejection_reason: Optional[str] = None
    ) -> ApprovalRequest:
        """Handle user response to approval request."""
        self.logger.info(f"Handling approval response for request {request_id}: {'approved' if approved else 'rejected'}")
        
        approval_request = self._pending_requests.get(request_id)
        if not approval_request:
            raise ValueError(f"Approval request {request_id} not found")
        
        if approval_request.is_expired():
            approval_request.status = ApprovalStatus.EXPIRED
            raise ValueError(f"Approval request {request_id} has expired")
        
        try:
            if approved:
                if modifications:
                    approval_request.modify(modifications)
                else:
                    approval_request.approve()
            else:
                approval_request.reject(rejection_reason or "No reason provided")
            
            # Execute callback if registered
            callback = self._approval_callbacks.get(request_id)
            if callback:
                await callback(approval_request)
                del self._approval_callbacks[request_id]
            
            # Publish response event
            await self.state_manager.publish_event({
                "event_id": f"approval_response_{request_id}",
                "source_agent": "user",
                "event_type": EventType.USER_INTERVENTION_REQUIRED,
                "payload": {
                    "approval_request_id": request_id,
                    "project_id": approval_request.project_id,
                    "status": approval_request.status.value,
                    "response_data": approval_request.response_data
                },
                "timestamp": datetime.utcnow()
            })
            
            self.logger.info(f"Approval response processed: {request_id} -> {approval_request.status.value}")
            return approval_request
            
        except Exception as e:
            self.logger.error(f"Failed to handle approval response: {str(e)}")
            raise
    
    def register_approval_callback(self, request_id: str, callback: Callable) -> None:
        """Register a callback to be executed when approval is received."""
        self._approval_callbacks[request_id] = callback
    
    def get_pending_approvals(self, project_id: Optional[str] = None) -> List[ApprovalRequest]:
        """Get pending approval requests, optionally filtered by project."""
        pending = [
            req for req in self._pending_requests.values()
            if req.status == ApprovalStatus.PENDING and not req.is_expired()
        ]
        
        if project_id:
            pending = [req for req in pending if req.project_id == project_id]
        
        return pending
    
    def _create_execution_plan_presentation(
        self, 
        execution_plan: Dict[str, Any], 
        project_request: ProjectRequest
    ) -> ExecutionPlanPresentation:
        """Create a user-friendly presentation of the execution plan."""
        
        # Extract key information from execution plan
        total_tasks = execution_plan.get("total_tasks", 0)
        metrics = execution_plan.get("metrics", {})
        schedules = execution_plan.get("schedules", [])
        resource_requirements = execution_plan.get("resource_requirements", {})
        
        # Format duration
        total_duration_minutes = metrics.get("total_duration_minutes", 0)
        hours = int(total_duration_minutes // 60)
        minutes = int(total_duration_minutes % 60)
        duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        
        # Create task breakdown
        task_breakdown = []
        for schedule in schedules[:10]:  # Show first 10 tasks
            task_breakdown.append({
                "task_id": schedule.get("task_id", ""),
                "description": schedule.get("assigned_agent", "Unknown") + " task",
                "estimated_duration": f"{schedule.get('duration', {}).get('total_seconds', 0) // 60:.0f}m",
                "start_time": schedule.get("execution_window", {}).get("start_time", ""),
                "dependencies": len(schedule.get("dependencies", []))
            })
        
        if len(schedules) > 10:
            task_breakdown.append({
                "task_id": "...",
                "description": f"... and {len(schedules) - 10} more tasks",
                "estimated_duration": "",
                "start_time": "",
                "dependencies": 0
            })
        
        # Identify risks and considerations
        risks = []
        if metrics.get("max_concurrent_tasks", 0) > 3:
            risks.append("High parallelism may require significant system resources")
        
        if total_duration_minutes > 120:  # More than 2 hours
            risks.append("Long execution time - consider breaking into phases")
        
        if resource_requirements.get("resource_utilization", {}).get("cpu_intensive_tasks", 0) > 5:
            risks.append("Multiple CPU-intensive tasks may slow down execution")
        
        if not risks:
            risks.append("No significant risks identified")
        
        return ExecutionPlanPresentation(
            project_summary=f"Building {project_request.description}",
            total_tasks=total_tasks,
            estimated_duration=duration_str,
            execution_strategy=execution_plan.get("strategy", "hybrid"),
            task_breakdown=task_breakdown,
            resource_requirements={
                "max_parallel_tasks": resource_requirements.get("max_parallel_tasks", 1),
                "total_duration": duration_str,
                "efficiency_gain": f"{resource_requirements.get('efficiency_gain', 0) * 100:.1f}%"
            },
            risks_and_considerations=risks,
            approval_options=[
                "Approve as presented",
                "Approve with modifications", 
                "Request changes",
                "Reject plan"
            ]
        )
    
    async def cleanup_expired_requests(self) -> int:
        """Clean up expired approval requests."""
        expired_count = 0
        expired_requests = []
        
        for request_id, request in self._pending_requests.items():
            if request.is_expired() and request.status == ApprovalStatus.PENDING:
                request.status = ApprovalStatus.EXPIRED
                expired_requests.append(request_id)
                expired_count += 1
        
        # Remove expired requests
        for request_id in expired_requests:
            del self._pending_requests[request_id]
            if request_id in self._approval_callbacks:
                del self._approval_callbacks[request_id]
        
        if expired_count > 0:
            self.logger.info(f"Cleaned up {expired_count} expired approval requests")
        
        return expired_count
    
    def get_approval_status(self, request_id: str) -> Optional[ApprovalStatus]:
        """Get the status of an approval request."""
        request = self._pending_requests.get(request_id)
        return request.status if request else None