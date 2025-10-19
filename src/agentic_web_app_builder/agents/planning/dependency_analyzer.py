"""Dependency analysis and resolution for task planning."""

import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum

from ...models.project import Task as TaskModel, TaskType


logger = logging.getLogger(__name__)


class DependencyType(Enum):
    """Types of dependencies between tasks."""
    HARD = "hard"  # Task cannot start until dependency is complete
    SOFT = "soft"  # Task can start but may be more efficient after dependency
    RESOURCE = "resource"  # Tasks compete for the same resource


@dataclass
class DependencyRelation:
    """Represents a dependency relationship between tasks."""
    from_task: str
    to_task: str
    dependency_type: DependencyType
    reason: str


class DependencyGraph:
    """Graph representation of task dependencies."""
    
    def __init__(self, tasks: List[TaskModel]):
        self.tasks = {task.id: task for task in tasks}
        self.dependencies: Dict[str, List[DependencyRelation]] = {}
        self._build_dependency_graph()
    
    def _build_dependency_graph(self) -> None:
        """Build the dependency graph from task dependencies."""
        for task in self.tasks.values():
            self.dependencies[task.id] = []
            
            # Add explicit dependencies
            for dep_id in task.dependencies:
                if dep_id in self.tasks:
                    relation = DependencyRelation(
                        from_task=dep_id,
                        to_task=task.id,
                        dependency_type=DependencyType.HARD,
                        reason="Explicit dependency"
                    )
                    self.dependencies[task.id].append(relation)
            
            # Add implicit dependencies based on task types
            self._add_implicit_dependencies(task)
    
    def _add_implicit_dependencies(self, task: TaskModel) -> None:
        """Add implicit dependencies based on task types and logic."""
        # Repository setup should come before code generation
        if task.type == TaskType.CODE_GENERATION:
            for other_task in self.tasks.values():
                if (other_task.type == TaskType.REPOSITORY_SETUP and 
                    other_task.id not in task.dependencies):
                    relation = DependencyRelation(
                        from_task=other_task.id,
                        to_task=task.id,
                        dependency_type=DependencyType.HARD,
                        reason="Repository must be set up before code generation"
                    )
                    self.dependencies[task.id].append(relation)
        
        # Testing should come after code generation
        if task.type == TaskType.TESTING:
            for other_task in self.tasks.values():
                if (other_task.type == TaskType.CODE_GENERATION and 
                    other_task.id not in task.dependencies):
                    relation = DependencyRelation(
                        from_task=other_task.id,
                        to_task=task.id,
                        dependency_type=DependencyType.HARD,
                        reason="Code must be generated before testing"
                    )
                    self.dependencies[task.id].append(relation)
        
        # Deployment should come after testing
        if task.type == TaskType.DEPLOYMENT:
            for other_task in self.tasks.values():
                if (other_task.type == TaskType.TESTING and 
                    other_task.id not in task.dependencies):
                    relation = DependencyRelation(
                        from_task=other_task.id,
                        to_task=task.id,
                        dependency_type=DependencyType.HARD,
                        reason="Testing must pass before deployment"
                    )
                    self.dependencies[task.id].append(relation)
        
        # Monitoring setup should come after deployment
        if task.type == TaskType.MONITORING_SETUP:
            for other_task in self.tasks.values():
                if (other_task.type == TaskType.DEPLOYMENT and 
                    other_task.id not in task.dependencies):
                    relation = DependencyRelation(
                        from_task=other_task.id,
                        to_task=task.id,
                        dependency_type=DependencyType.HARD,
                        reason="Application must be deployed before monitoring setup"
                    )
                    self.dependencies[task.id].append(relation)
    
    def detect_cycles(self) -> List[List[str]]:
        """Detect circular dependencies in the graph."""
        cycles = []
        visited = set()
        rec_stack = set()
        
        def dfs(task_id: str, path: List[str]) -> None:
            if task_id in rec_stack:
                # Found a cycle
                cycle_start = path.index(task_id)
                cycle = path[cycle_start:] + [task_id]
                cycles.append(cycle)
                return
            
            if task_id in visited:
                return
            
            visited.add(task_id)
            rec_stack.add(task_id)
            path.append(task_id)
            
            # Visit all dependencies
            for relation in self.dependencies.get(task_id, []):
                if relation.dependency_type == DependencyType.HARD:
                    dfs(relation.from_task, path.copy())
            
            rec_stack.remove(task_id)
        
        for task_id in self.tasks:
            if task_id not in visited:
                dfs(task_id, [])
        
        return cycles
    
    def topological_sort(self) -> List[str]:
        """Perform topological sort to get execution order."""
        # Check for cycles first
        cycles = self.detect_cycles()
        if cycles:
            raise ValueError(f"Circular dependencies detected: {cycles}")
        
        in_degree = {task_id: 0 for task_id in self.tasks}
        
        # Calculate in-degrees
        for task_id in self.tasks:
            for relation in self.dependencies.get(task_id, []):
                if relation.dependency_type == DependencyType.HARD:
                    in_degree[task_id] += 1
        
        # Kahn's algorithm
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            current = queue.pop(0)
            result.append(current)
            
            # Update in-degrees of dependent tasks
            for task_id in self.tasks:
                for relation in self.dependencies.get(task_id, []):
                    if (relation.from_task == current and 
                        relation.dependency_type == DependencyType.HARD):
                        in_degree[task_id] -= 1
                        if in_degree[task_id] == 0:
                            queue.append(task_id)
        
        if len(result) != len(self.tasks):
            raise ValueError("Failed to resolve all dependencies")
        
        return result
    
    def get_parallel_groups(self) -> List[List[str]]:
        """Group tasks that can be executed in parallel."""
        execution_order = self.topological_sort()
        groups = []
        remaining_tasks = set(execution_order)
        
        while remaining_tasks:
            # Find tasks with no unresolved dependencies
            current_group = []
            for task_id in remaining_tasks:
                can_execute = True
                for relation in self.dependencies.get(task_id, []):
                    if (relation.dependency_type == DependencyType.HARD and 
                        relation.from_task in remaining_tasks):
                        can_execute = False
                        break
                
                if can_execute:
                    current_group.append(task_id)
            
            if not current_group:
                raise ValueError("Unable to find executable tasks - possible dependency issue")
            
            groups.append(current_group)
            remaining_tasks -= set(current_group)
        
        return groups


class DependencyAnalyzer:
    """Analyzes and resolves task dependencies."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def analyze_dependencies(self, tasks: List[TaskModel]) -> DependencyGraph:
        """Analyze task dependencies and create dependency graph."""
        self.logger.info(f"Analyzing dependencies for {len(tasks)} tasks")
        
        try:
            graph = DependencyGraph(tasks)
            
            # Validate the graph
            cycles = graph.detect_cycles()
            if cycles:
                self.logger.error(f"Circular dependencies detected: {cycles}")
                raise ValueError(f"Circular dependencies found: {cycles}")
            
            self.logger.info("Dependency analysis completed successfully")
            return graph
            
        except Exception as e:
            self.logger.error(f"Dependency analysis failed: {str(e)}")
            raise
    
    def optimize_execution_order(self, graph: DependencyGraph) -> List[str]:
        """Optimize task execution order for efficiency."""
        self.logger.info("Optimizing execution order")
        
        try:
            # Get basic topological order
            base_order = graph.topological_sort()
            
            # Apply optimization heuristics
            optimized_order = self._apply_optimization_heuristics(graph, base_order)
            
            self.logger.info(f"Execution order optimized: {optimized_order}")
            return optimized_order
            
        except Exception as e:
            self.logger.error(f"Execution order optimization failed: {str(e)}")
            raise
    
    def _apply_optimization_heuristics(self, graph: DependencyGraph, base_order: List[str]) -> List[str]:
        """Apply heuristics to optimize execution order."""
        # Simple heuristic: prioritize shorter tasks when there's no dependency constraint
        tasks_by_duration = sorted(
            graph.tasks.values(),
            key=lambda t: t.estimated_duration.total_seconds() if t.estimated_duration else 0
        )
        
        optimized = []
        remaining = set(base_order)
        
        while remaining:
            # Find tasks that can be executed now
            available = []
            for task_id in remaining:
                can_execute = True
                for relation in graph.dependencies.get(task_id, []):
                    if (relation.dependency_type == DependencyType.HARD and 
                        relation.from_task in remaining):
                        can_execute = False
                        break
                
                if can_execute:
                    available.append(task_id)
            
            if not available:
                # Fallback to original order
                optimized.extend(remaining)
                break
            
            # Sort available tasks by duration (shortest first)
            available.sort(key=lambda tid: (
                graph.tasks[tid].estimated_duration.total_seconds() 
                if graph.tasks[tid].estimated_duration else 0
            ))
            
            # Take the shortest task
            next_task = available[0]
            optimized.append(next_task)
            remaining.remove(next_task)
        
        return optimized
    
    def estimate_resource_requirements(self, graph: DependencyGraph) -> Dict[str, Any]:
        """Estimate resource requirements for the execution plan."""
        self.logger.info("Estimating resource requirements")
        
        parallel_groups = graph.get_parallel_groups()
        max_parallel_tasks = max(len(group) for group in parallel_groups) if parallel_groups else 1
        
        total_duration = sum(
            task.estimated_duration.total_seconds() / 60
            for task in graph.tasks.values()
            if task.estimated_duration
        )
        
        # Estimate parallel execution time
        parallel_duration = 0
        for group in parallel_groups:
            group_duration = max(
                graph.tasks[task_id].estimated_duration.total_seconds() / 60
                for task_id in group
                if graph.tasks[task_id].estimated_duration
            ) if group else 0
            parallel_duration += group_duration
        
        return {
            "max_parallel_tasks": max_parallel_tasks,
            "total_duration_minutes": total_duration,
            "parallel_duration_minutes": parallel_duration,
            "efficiency_gain": (total_duration - parallel_duration) / total_duration if total_duration > 0 else 0,
            "parallel_groups": len(parallel_groups),
            "resource_utilization": {
                "cpu_intensive_tasks": len([
                    t for t in graph.tasks.values() 
                    if t.type in [TaskType.CODE_GENERATION, TaskType.TESTING]
                ]),
                "io_intensive_tasks": len([
                    t for t in graph.tasks.values() 
                    if t.type in [TaskType.DEPLOYMENT, TaskType.REPOSITORY_SETUP]
                ]),
                "monitoring_tasks": len([
                    t for t in graph.tasks.values() 
                    if t.type == TaskType.MONITORING_SETUP
                ])
            }
        }