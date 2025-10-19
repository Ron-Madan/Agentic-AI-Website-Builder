"""Planner Agent implementation for task decomposition and execution planning."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..agents.base import PlannerAgentBase
from ..core.interfaces import Task, TaskType, TaskStatus, EventType, AgentEvent
from ..models.project import ProjectRequest, ProjectState, Task as TaskModel
from ..tools.llm_service import LLMService
from ..core.config import get_settings
from .planning import DependencyAnalyzer, ExecutionPlanner, ExecutionStrategy, ApprovalWorkflow


logger = logging.getLogger(__name__)


class TaskPlan(object):
    """Represents a complete task plan for a project."""
    
    def __init__(self, project_id: str, tasks: List[TaskModel], metadata: Optional[Dict[str, Any]] = None):
        self.project_id = project_id
        self.tasks = tasks
        self.metadata = metadata or {}
        self.created_at = datetime.utcnow()
    
    def get_execution_order(self) -> List[str]:
        """Get the optimal execution order for tasks based on dependencies."""
        # Simple topological sort for task dependencies
        visited = set()
        temp_visited = set()
        result = []
        
        def visit(task_id: str):
            if task_id in temp_visited:
                raise ValueError(f"Circular dependency detected involving task {task_id}")
            if task_id in visited:
                return
            
            temp_visited.add(task_id)
            
            # Find the task object
            task = next((t for t in self.tasks if t.id == task_id), None)
            if task:
                # Visit all dependencies first
                for dep_id in task.dependencies:
                    visit(dep_id)
            
            temp_visited.remove(task_id)
            visited.add(task_id)
            result.append(task_id)
        
        # Visit all tasks
        for task in self.tasks:
            if task.id not in visited:
                visit(task.id)
        
        return result
    
    def estimate_total_duration(self) -> timedelta:
        """Estimate total project duration considering dependencies."""
        execution_order = self.get_execution_order()
        
        # Simple estimation: sum of all task durations
        # In reality, some tasks could run in parallel
        total_minutes = sum(
            task.estimated_duration.total_seconds() / 60 
            for task in self.tasks 
            if task.estimated_duration
        )
        
        return timedelta(minutes=total_minutes)


class ExecutionPlan(object):
    """Represents an execution plan with user approval status."""
    
    def __init__(self, task_plan: TaskPlan, user_approved: bool = False):
        self.task_plan = task_plan
        self.user_approved = user_approved
        self.execution_order = task_plan.get_execution_order()
        self.estimated_duration = task_plan.estimate_total_duration()
        self.created_at = datetime.utcnow()
        self.approved_at: Optional[datetime] = None
    
    def approve(self) -> None:
        """Mark the execution plan as approved by the user."""
        self.user_approved = True
        self.approved_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert execution plan to dictionary for presentation."""
        return {
            "project_id": self.task_plan.project_id,
            "total_tasks": len(self.task_plan.tasks),
            "estimated_duration_minutes": int(self.estimated_duration.total_seconds() / 60),
            "execution_order": self.execution_order,
            "tasks": [
                {
                    "id": task.id,
                    "type": task.type.value,
                    "description": task.description,
                    "dependencies": task.dependencies,
                    "estimated_duration_minutes": int(task.estimated_duration.total_seconds() / 60) if task.estimated_duration else 0,
                    "agent_assigned": task.agent_assigned
                }
                for task in self.task_plan.tasks
            ],
            "user_approved": self.user_approved,
            "created_at": self.created_at.isoformat(),
            "approved_at": self.approved_at.isoformat() if self.approved_at else None
        }


class PlannerAgent(PlannerAgentBase):
    """Planner Agent responsible for analyzing requirements and creating execution plans."""
    
    def __init__(self, state_manager: 'StateManager'):
        super().__init__(state_manager)
        self.llm_service = LLMService()
        self.settings = get_settings()
        self.dependency_analyzer = DependencyAnalyzer()
        self.execution_planner = ExecutionPlanner(
            max_parallel_tasks=getattr(self.settings, 'max_concurrent_tasks', 3)
        )
        self.approval_workflow = ApprovalWorkflow(state_manager)
        self._pending_approvals: Dict[str, ExecutionPlan] = {}
    
    async def _execute_task_impl(self, task: Task) -> Dict[str, Any]:
        """Execute planner-specific tasks."""
        if task.type == TaskType.USER_APPROVAL:
            return await self._handle_user_approval_task(task)
        else:
            raise ValueError(f"Unsupported task type for PlannerAgent: {task.type}")
    
    async def analyze_user_request(self, request: ProjectRequest) -> Dict[str, Any]:
        """Analyze user request and extract structured requirements."""
        self.logger.info(f"Analyzing user request: {request.description}")
        
        try:
            # Use LLM service to analyze requirements
            analysis = await self.llm_service.analyze_user_requirements(
                request.description, 
                request.requirements
            )
            
            self.logger.info(f"Requirements analysis completed with confidence: {analysis.get('confidence_score', 0)}")
            
            # Store analysis in project metadata
            project_state = await self.state_manager.get_project_state(request.user_id)
            if project_state:
                project_state['requirements_analysis'] = analysis
                await self.state_manager.store_project_state(request.user_id, project_state)
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Failed to analyze user request: {str(e)}")
            raise
    
    async def decompose_into_subtasks(self, project_id: str, analysis: Dict[str, Any], description: str) -> List[TaskModel]:
        """Decompose project requirements into specific subtasks."""
        self.logger.info(f"Decomposing project {project_id} into subtasks")
        
        try:
            # Use LLM service to generate task breakdown
            task_data = await self.llm_service.decompose_into_tasks(analysis, description)
            
            # Convert to TaskModel objects
            tasks = []
            for task_info in task_data:
                task = TaskModel(
                    id=f"{project_id}_{task_info.get('id', str(uuid.uuid4()))}",
                    project_id=project_id,
                    type=TaskType(task_info.get('type', 'code_generation')),
                    description=task_info.get('description', ''),
                    dependencies=[f"{project_id}_{dep}" for dep in task_info.get('dependencies', [])],
                    estimated_duration=timedelta(minutes=task_info.get('estimated_duration_minutes', 30)),
                    status=TaskStatus.PENDING,
                    agent_assigned=task_info.get('agent_assigned', 'developer')
                )
                tasks.append(task)
            
            self.logger.info(f"Generated {len(tasks)} subtasks for project {project_id}")
            return tasks
            
        except Exception as e:
            self.logger.error(f"Failed to decompose project into subtasks: {str(e)}")
            raise
    
    async def determine_execution_order(self, tasks: List[TaskModel]) -> TaskPlan:
        """Determine optimal execution order and create task plan."""
        self.logger.info(f"Determining execution order for {len(tasks)} tasks")
        
        try:
            # Use dependency analyzer for sophisticated dependency analysis
            dependency_graph = self.dependency_analyzer.analyze_dependencies(tasks)
            
            # Get optimized execution order
            execution_order = self.dependency_analyzer.optimize_execution_order(dependency_graph)
            
            # Create task plan with enhanced metadata
            project_id = tasks[0].project_id if tasks else "unknown"
            
            # Create execution plan using execution planner
            execution_plan_data = self.execution_planner.create_execution_plan(
                tasks, ExecutionStrategy.HYBRID
            )
            
            task_plan = TaskPlan(project_id, tasks, {
                "execution_order": execution_order,
                "dependency_analysis": {
                    "total_dependencies": len([
                        rel for task_deps in dependency_graph.dependencies.values() 
                        for rel in task_deps
                    ]),
                    "parallel_groups": len(dependency_graph.get_parallel_groups()),
                },
                "execution_plan": execution_plan_data,
                "resource_requirements": self.dependency_analyzer.estimate_resource_requirements(dependency_graph)
            })
            
            self.logger.info(f"Execution order determined with {len(execution_order)} tasks")
            return task_plan
            
        except Exception as e:
            self.logger.error(f"Failed to determine execution order: {str(e)}")
            raise
    
    async def create_execution_plan(self, project_request: ProjectRequest) -> ExecutionPlan:
        """Create a complete execution plan from user request."""
        self.logger.info(f"Creating execution plan for project: {project_request.description}")
        
        try:
            # Step 1: Analyze user requirements
            analysis = await self.analyze_user_request(project_request)
            
            # Step 2: Decompose into subtasks
            tasks = await self.decompose_into_subtasks(
                project_request.user_id, 
                analysis, 
                project_request.description
            )
            
            # Step 3: Determine execution order
            task_plan = await self.determine_execution_order(tasks)
            
            # Step 4: Create execution plan
            execution_plan = ExecutionPlan(task_plan)
            
            # Store the plan for user approval
            self._pending_approvals[project_request.user_id] = execution_plan
            
            self.logger.info(f"Execution plan created for project {project_request.user_id}")
            return execution_plan
            
        except Exception as e:
            self.logger.error(f"Failed to create execution plan: {str(e)}")
            raise
    
    async def request_user_approval(self, project_id: str, project_request: ProjectRequest) -> str:
        """Request user approval for execution plan."""
        self.logger.info(f"Requesting user approval for project {project_id}")
        
        execution_plan = self._pending_approvals.get(project_id)
        if not execution_plan:
            raise ValueError(f"No pending execution plan found for project {project_id}")
        
        try:
            # Use approval workflow to request approval
            approval_request = await self.approval_workflow.request_execution_plan_approval(
                project_id, 
                execution_plan.to_dict(),
                project_request
            )
            
            # Register callback for when approval is received
            self.approval_workflow.register_approval_callback(
                approval_request.request_id,
                self._handle_approval_callback
            )
            
            self.logger.info(f"User approval requested: {approval_request.request_id}")
            return approval_request.request_id
            
        except Exception as e:
            self.logger.error(f"Failed to request user approval: {str(e)}")
            raise
    
    async def handle_user_approval(self, request_id: str, approved: bool, modifications: Optional[Dict[str, Any]] = None, rejection_reason: Optional[str] = None) -> ExecutionPlan:
        """Handle user approval response."""
        self.logger.info(f"Handling user approval for request {request_id}: {'approved' if approved else 'rejected'}")
        
        try:
            # Process approval through workflow
            approval_request = await self.approval_workflow.handle_approval_response(
                request_id, approved, modifications, rejection_reason
            )
            
            project_id = approval_request.project_id
            execution_plan = self._pending_approvals.get(project_id)
            
            if not execution_plan:
                raise ValueError(f"No pending execution plan found for project {project_id}")
            
            if approved:
                # Apply any user modifications
                if modifications:
                    await self._apply_plan_modifications(execution_plan, modifications)
                
                # Approve the plan
                execution_plan.approve()
                
                # Store the approved plan in project state
                project_state = await self.state_manager.get_project_state(project_id)
                if project_state:
                    project_state['execution_plan'] = execution_plan.to_dict()
                    project_state['pending_tasks'] = [task.dict() for task in execution_plan.task_plan.tasks]
                    project_state['approval_request_id'] = request_id
                    await self.state_manager.store_project_state(project_id, project_state)
                
                # Remove from pending approvals
                del self._pending_approvals[project_id]
                
                self.logger.info(f"Execution plan approved for project {project_id}")
                
            else:
                # Plan was rejected, keep it pending for modifications
                self.logger.info(f"Execution plan rejected for project {project_id}: {rejection_reason}")
            
            return execution_plan
            
        except Exception as e:
            self.logger.error(f"Failed to handle user approval: {str(e)}")
            raise
    
    async def _apply_plan_modifications(self, execution_plan: ExecutionPlan, modifications: Dict[str, Any]) -> None:
        """Apply user modifications to the execution plan."""
        self.logger.info("Applying user modifications to execution plan")
        
        # This is a simplified implementation
        # In a real system, you'd want more sophisticated modification handling
        if 'task_modifications' in modifications:
            for task_mod in modifications['task_modifications']:
                task_id = task_mod.get('task_id')
                task = next((t for t in execution_plan.task_plan.tasks if t.id == task_id), None)
                if task:
                    if 'description' in task_mod:
                        task.description = task_mod['description']
                    if 'estimated_duration_minutes' in task_mod:
                        task.estimated_duration = timedelta(minutes=task_mod['estimated_duration_minutes'])
        
        # Recalculate execution order and duration
        execution_plan.execution_order = execution_plan.task_plan.get_execution_order()
        execution_plan.estimated_duration = execution_plan.task_plan.estimate_total_duration()
    
    async def _handle_user_approval_task(self, task: Task) -> Dict[str, Any]:
        """Handle a user approval task."""
        # This would typically wait for user input through the API
        # For now, we'll return a placeholder result
        return {
            "status": "pending_user_input",
            "message": "Waiting for user approval"
        }
    
    async def _handle_approval_callback(self, approval_request) -> None:
        """Handle approval callback when user responds."""
        self.logger.info(f"Processing approval callback for request {approval_request.request_id}")
        
        try:
            project_id = approval_request.project_id
            
            if approval_request.status.value == "approved":
                # Trigger next phase of execution
                await self.publish_event(EventType.TASK_COMPLETED, {
                    "project_id": project_id,
                    "task_type": "execution_plan_approval",
                    "approval_request_id": approval_request.request_id,
                    "message": "Execution plan approved, ready to begin implementation"
                })
                
            elif approval_request.status.value == "modified":
                # Handle plan modifications
                modifications = approval_request.response_data.get("modifications", {})
                self.logger.info(f"Applying user modifications to project {project_id}")
                
                # Re-create execution plan with modifications
                execution_plan = self._pending_approvals.get(project_id)
                if execution_plan and modifications:
                    await self._apply_plan_modifications(execution_plan, modifications)
                
            elif approval_request.status.value == "rejected":
                # Handle rejection
                reason = approval_request.response_data.get("rejection_reason", "No reason provided")
                self.logger.info(f"Execution plan rejected for project {project_id}: {reason}")
                
                await self.publish_event(EventType.USER_INTERVENTION_REQUIRED, {
                    "project_id": project_id,
                    "intervention_type": "plan_revision_needed",
                    "rejection_reason": reason,
                    "message": "Execution plan was rejected. Please provide new requirements or modifications."
                })
                
        except Exception as e:
            self.logger.error(f"Error in approval callback: {str(e)}")
    
    async def get_pending_approvals(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get pending approval requests."""
        try:
            pending_requests = self.approval_workflow.get_pending_approvals(project_id)
            return [
                {
                    "request_id": req.request_id,
                    "project_id": req.project_id,
                    "title": req.title,
                    "description": req.description,
                    "created_at": req.created_at.isoformat(),
                    "expires_at": req.expires_at.isoformat() if req.expires_at else None,
                    "presentation": req.data.get("presentation", {})
                }
                for req in pending_requests
            ]
        except Exception as e:
            self.logger.error(f"Failed to get pending approvals: {str(e)}")
            return []
    
    async def handle_event(self, event: AgentEvent) -> None:
        """Handle incoming events."""
        await super().handle_event(event)
        
        if event.event_type == EventType.USER_INTERVENTION_REQUIRED:
            # Handle user intervention events if they're related to planning
            payload = event.payload
            if payload.get('intervention_type') == 'execution_plan_approval':
                project_id = payload.get('project_id')
                if project_id in self._pending_approvals:
                    self.logger.info(f"User intervention required for project {project_id}")
        
        # Cleanup expired approval requests periodically
        await self.approval_workflow.cleanup_expired_requests()