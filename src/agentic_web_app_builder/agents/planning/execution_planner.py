"""Execution planning and resource optimization for task execution."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ...models.project import Task as TaskModel, TaskType, TaskStatus
from .dependency_analyzer import DependencyAnalyzer, DependencyGraph


logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """Types of resources that tasks can consume."""
    CPU = "cpu"
    MEMORY = "memory"
    NETWORK = "network"
    STORAGE = "storage"
    API_QUOTA = "api_quota"


@dataclass
class ResourceRequirement:
    """Resource requirement for a task."""
    resource_type: ResourceType
    amount: float
    unit: str


@dataclass
class ExecutionWindow:
    """Time window for task execution."""
    start_time: datetime
    end_time: datetime
    duration: timedelta


@dataclass
class TaskSchedule:
    """Schedule for a specific task."""
    task_id: str
    execution_window: ExecutionWindow
    assigned_agent: str
    resource_allocation: Dict[ResourceType, float]
    dependencies_resolved: bool = False


class ExecutionStrategy(Enum):
    """Strategies for task execution."""
    SEQUENTIAL = "sequential"  # Execute tasks one by one
    PARALLEL = "parallel"  # Execute tasks in parallel when possible
    HYBRID = "hybrid"  # Mix of sequential and parallel based on resources
    PRIORITY_BASED = "priority_based"  # Execute high-priority tasks first


class ExecutionPlanner:
    """Plans and optimizes task execution schedules."""
    
    def __init__(self, max_parallel_tasks: int = 3, available_resources: Optional[Dict[ResourceType, float]] = None):
        self.max_parallel_tasks = max_parallel_tasks
        self.available_resources = available_resources or {
            ResourceType.CPU: 4.0,  # 4 CPU cores
            ResourceType.MEMORY: 8.0,  # 8 GB RAM
            ResourceType.NETWORK: 100.0,  # 100 Mbps
            ResourceType.API_QUOTA: 1000.0  # 1000 API calls per hour
        }
        self.dependency_analyzer = DependencyAnalyzer()
        self.logger = logging.getLogger(__name__)
    
    def create_execution_plan(self, tasks: List[TaskModel], strategy: ExecutionStrategy = ExecutionStrategy.HYBRID) -> Dict[str, Any]:
        """Create an optimized execution plan for the given tasks."""
        self.logger.info(f"Creating execution plan for {len(tasks)} tasks using {strategy.value} strategy")
        
        try:
            # Analyze dependencies
            dependency_graph = self.dependency_analyzer.analyze_dependencies(tasks)
            
            # Create task schedules based on strategy
            if strategy == ExecutionStrategy.SEQUENTIAL:
                schedules = self._create_sequential_schedule(dependency_graph)
            elif strategy == ExecutionStrategy.PARALLEL:
                schedules = self._create_parallel_schedule(dependency_graph)
            elif strategy == ExecutionStrategy.HYBRID:
                schedules = self._create_hybrid_schedule(dependency_graph)
            elif strategy == ExecutionStrategy.PRIORITY_BASED:
                schedules = self._create_priority_based_schedule(dependency_graph)
            else:
                raise ValueError(f"Unsupported execution strategy: {strategy}")
            
            # Calculate execution metrics
            metrics = self._calculate_execution_metrics(schedules, dependency_graph)
            
            execution_plan = {
                "strategy": strategy.value,
                "total_tasks": len(tasks),
                "schedules": [schedule.__dict__ for schedule in schedules],
                "metrics": metrics,
                "resource_requirements": self.dependency_analyzer.estimate_resource_requirements(dependency_graph),
                "created_at": datetime.utcnow().isoformat()
            }
            
            self.logger.info(f"Execution plan created successfully with {len(schedules)} scheduled tasks")
            return execution_plan
            
        except Exception as e:
            self.logger.error(f"Failed to create execution plan: {str(e)}")
            raise
    
    def _create_sequential_schedule(self, graph: DependencyGraph) -> List[TaskSchedule]:
        """Create a sequential execution schedule."""
        execution_order = self.dependency_analyzer.optimize_execution_order(graph)
        schedules = []
        current_time = datetime.utcnow()
        
        for task_id in execution_order:
            task = graph.tasks[task_id]
            duration = task.estimated_duration or timedelta(minutes=30)
            
            schedule = TaskSchedule(
                task_id=task_id,
                execution_window=ExecutionWindow(
                    start_time=current_time,
                    end_time=current_time + duration,
                    duration=duration
                ),
                assigned_agent=task.agent_assigned or "default",
                resource_allocation=self._estimate_task_resources(task)
            )
            
            schedules.append(schedule)
            current_time += duration
        
        return schedules
    
    def _create_parallel_schedule(self, graph: DependencyGraph) -> List[TaskSchedule]:
        """Create a parallel execution schedule."""
        parallel_groups = graph.get_parallel_groups()
        schedules = []
        current_time = datetime.utcnow()
        
        for group in parallel_groups:
            # All tasks in a group start at the same time
            group_duration = max(
                graph.tasks[task_id].estimated_duration or timedelta(minutes=30)
                for task_id in group
            )
            
            for task_id in group:
                task = graph.tasks[task_id]
                duration = task.estimated_duration or timedelta(minutes=30)
                
                schedule = TaskSchedule(
                    task_id=task_id,
                    execution_window=ExecutionWindow(
                        start_time=current_time,
                        end_time=current_time + duration,
                        duration=duration
                    ),
                    assigned_agent=task.agent_assigned or "default",
                    resource_allocation=self._estimate_task_resources(task)
                )
                
                schedules.append(schedule)
            
            current_time += group_duration
        
        return schedules
    
    def _create_hybrid_schedule(self, graph: DependencyGraph) -> List[TaskSchedule]:
        """Create a hybrid execution schedule balancing parallelism and resources."""
        parallel_groups = graph.get_parallel_groups()
        schedules = []
        current_time = datetime.utcnow()
        
        for group in parallel_groups:
            # Limit parallelism based on available resources
            if len(group) <= self.max_parallel_tasks:
                # Execute all tasks in parallel
                group_duration = max(
                    graph.tasks[task_id].estimated_duration or timedelta(minutes=30)
                    for task_id in group
                )
                
                for task_id in group:
                    task = graph.tasks[task_id]
                    duration = task.estimated_duration or timedelta(minutes=30)
                    
                    schedule = TaskSchedule(
                        task_id=task_id,
                        execution_window=ExecutionWindow(
                            start_time=current_time,
                            end_time=current_time + duration,
                            duration=duration
                        ),
                        assigned_agent=task.agent_assigned or "default",
                        resource_allocation=self._estimate_task_resources(task)
                    )
                    
                    schedules.append(schedule)
                
                current_time += group_duration
            else:
                # Split group into smaller batches
                batches = [group[i:i + self.max_parallel_tasks] 
                          for i in range(0, len(group), self.max_parallel_tasks)]
                
                for batch in batches:
                    batch_duration = max(
                        graph.tasks[task_id].estimated_duration or timedelta(minutes=30)
                        for task_id in batch
                    )
                    
                    for task_id in batch:
                        task = graph.tasks[task_id]
                        duration = task.estimated_duration or timedelta(minutes=30)
                        
                        schedule = TaskSchedule(
                            task_id=task_id,
                            execution_window=ExecutionWindow(
                                start_time=current_time,
                                end_time=current_time + duration,
                                duration=duration
                            ),
                            assigned_agent=task.agent_assigned or "default",
                            resource_allocation=self._estimate_task_resources(task)
                        )
                        
                        schedules.append(schedule)
                    
                    current_time += batch_duration
        
        return schedules
    
    def _create_priority_based_schedule(self, graph: DependencyGraph) -> List[TaskSchedule]:
        """Create a priority-based execution schedule."""
        # Assign priorities based on task type and dependencies
        task_priorities = self._calculate_task_priorities(graph)
        
        # Sort tasks by priority while respecting dependencies
        execution_order = self._priority_aware_topological_sort(graph, task_priorities)
        
        schedules = []
        current_time = datetime.utcnow()
        
        for task_id in execution_order:
            task = graph.tasks[task_id]
            duration = task.estimated_duration or timedelta(minutes=30)
            
            schedule = TaskSchedule(
                task_id=task_id,
                execution_window=ExecutionWindow(
                    start_time=current_time,
                    end_time=current_time + duration,
                    duration=duration
                ),
                assigned_agent=task.agent_assigned or "default",
                resource_allocation=self._estimate_task_resources(task)
            )
            
            schedules.append(schedule)
            current_time += duration
        
        return schedules
    
    def _estimate_task_resources(self, task: TaskModel) -> Dict[ResourceType, float]:
        """Estimate resource requirements for a task."""
        # Basic resource estimation based on task type
        resource_profiles = {
            TaskType.CODE_GENERATION: {
                ResourceType.CPU: 2.0,
                ResourceType.MEMORY: 2.0,
                ResourceType.API_QUOTA: 50.0
            },
            TaskType.REPOSITORY_SETUP: {
                ResourceType.CPU: 0.5,
                ResourceType.MEMORY: 0.5,
                ResourceType.NETWORK: 10.0
            },
            TaskType.TESTING: {
                ResourceType.CPU: 1.5,
                ResourceType.MEMORY: 1.0,
                ResourceType.NETWORK: 5.0
            },
            TaskType.DEPLOYMENT: {
                ResourceType.CPU: 1.0,
                ResourceType.MEMORY: 1.0,
                ResourceType.NETWORK: 20.0
            },
            TaskType.MONITORING_SETUP: {
                ResourceType.CPU: 0.5,
                ResourceType.MEMORY: 0.5,
                ResourceType.NETWORK: 5.0
            }
        }
        
        return resource_profiles.get(task.type, {
            ResourceType.CPU: 1.0,
            ResourceType.MEMORY: 1.0,
            ResourceType.NETWORK: 5.0
        })
    
    def _calculate_task_priorities(self, graph: DependencyGraph) -> Dict[str, float]:
        """Calculate priority scores for tasks."""
        priorities = {}
        
        for task_id, task in graph.tasks.items():
            priority = 0.0
            
            # Base priority by task type
            type_priorities = {
                TaskType.REPOSITORY_SETUP: 10.0,
                TaskType.CODE_GENERATION: 8.0,
                TaskType.TESTING: 6.0,
                TaskType.DEPLOYMENT: 4.0,
                TaskType.MONITORING_SETUP: 2.0,
                TaskType.USER_APPROVAL: 9.0
            }
            priority += type_priorities.get(task.type, 5.0)
            
            # Increase priority for tasks with many dependents
            dependent_count = sum(
                1 for other_task_id in graph.tasks
                for relation in graph.dependencies.get(other_task_id, [])
                if relation.from_task == task_id
            )
            priority += dependent_count * 2.0
            
            # Decrease priority for longer tasks (to get quick wins first)
            if task.estimated_duration:
                duration_minutes = task.estimated_duration.total_seconds() / 60
                priority -= duration_minutes * 0.1
            
            priorities[task_id] = priority
        
        return priorities
    
    def _priority_aware_topological_sort(self, graph: DependencyGraph, priorities: Dict[str, float]) -> List[str]:
        """Perform topological sort with priority consideration."""
        in_degree = {task_id: 0 for task_id in graph.tasks}
        
        # Calculate in-degrees
        for task_id in graph.tasks:
            for relation in graph.dependencies.get(task_id, []):
                in_degree[task_id] += 1
        
        # Priority queue (higher priority first)
        available = [(priorities.get(task_id, 0), task_id) 
                    for task_id, degree in in_degree.items() if degree == 0]
        available.sort(reverse=True)  # Sort by priority descending
        
        result = []
        
        while available:
            _, current = available.pop(0)
            result.append(current)
            
            # Update in-degrees and add newly available tasks
            newly_available = []
            for task_id in graph.tasks:
                for relation in graph.dependencies.get(task_id, []):
                    if relation.from_task == current:
                        in_degree[task_id] -= 1
                        if in_degree[task_id] == 0:
                            newly_available.append((priorities.get(task_id, 0), task_id))
            
            # Add newly available tasks and re-sort
            available.extend(newly_available)
            available.sort(reverse=True)
        
        return result
    
    def _calculate_execution_metrics(self, schedules: List[TaskSchedule], graph: DependencyGraph) -> Dict[str, Any]:
        """Calculate metrics for the execution plan."""
        if not schedules:
            return {}
        
        total_duration = max(schedule.execution_window.end_time for schedule in schedules) - \
                        min(schedule.execution_window.start_time for schedule in schedules)
        
        sequential_duration = sum(
            task.estimated_duration.total_seconds() / 60
            for task in graph.tasks.values()
            if task.estimated_duration
        )
        
        parallel_efficiency = 1.0 - (total_duration.total_seconds() / 60) / sequential_duration if sequential_duration > 0 else 0
        
        # Resource utilization
        max_concurrent_tasks = 0
        time_points = []
        for schedule in schedules:
            time_points.append((schedule.execution_window.start_time, 1))  # Task starts
            time_points.append((schedule.execution_window.end_time, -1))   # Task ends
        
        time_points.sort()
        current_tasks = 0
        for _, delta in time_points:
            current_tasks += delta
            max_concurrent_tasks = max(max_concurrent_tasks, current_tasks)
        
        return {
            "total_duration_minutes": total_duration.total_seconds() / 60,
            "sequential_duration_minutes": sequential_duration,
            "parallel_efficiency": parallel_efficiency,
            "max_concurrent_tasks": max_concurrent_tasks,
            "average_task_duration_minutes": sequential_duration / len(graph.tasks) if graph.tasks else 0,
            "resource_utilization": max_concurrent_tasks / self.max_parallel_tasks if self.max_parallel_tasks > 0 else 0
        }