"""Developer Agent implementation with tool integrations."""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Type
from datetime import datetime
from abc import ABC, abstractmethod

from .base import DeveloperAgentBase
from ..core.interfaces import Task, TaskType, EventType, ToolInterface
from ..models.project import ProjectStructure, ComponentSpecs, CodeFiles, Repository, DeploymentConfig, DeploymentResult
from ..tools.interfaces import CodeGenerationTool, GitTool, DeploymentTool


logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for managing tool instances and selection."""
    
    def __init__(self):
        self._tools: Dict[str, Dict[str, ToolInterface]] = {
            "code_generation": {},
            "git": {},
            "deployment": {}
        }
        self._default_tools: Dict[str, str] = {}
    
    def register_tool(self, category: str, name: str, tool: ToolInterface) -> None:
        """Register a tool in the registry."""
        if category not in self._tools:
            self._tools[category] = {}
        self._tools[category][name] = tool
        logger.info(f"Registered {category} tool: {name}")
    
    def set_default_tool(self, category: str, name: str) -> None:
        """Set the default tool for a category."""
        if category in self._tools and name in self._tools[category]:
            self._default_tools[category] = name
            logger.info(f"Set default {category} tool to: {name}")
        else:
            raise ValueError(f"Tool {name} not found in category {category}")
    
    def get_tool(self, category: str, name: Optional[str] = None) -> ToolInterface:
        """Get a tool by category and name."""
        if category not in self._tools:
            raise ValueError(f"Unknown tool category: {category}")
        
        tool_name = name or self._default_tools.get(category)
        if not tool_name:
            raise ValueError(f"No default tool set for category: {category}")
        
        if tool_name not in self._tools[category]:
            raise ValueError(f"Tool {tool_name} not found in category {category}")
        
        return self._tools[category][tool_name]
    
    def list_tools(self, category: Optional[str] = None) -> Dict[str, List[str]]:
        """List available tools by category."""
        if category:
            return {category: list(self._tools.get(category, {}).keys())}
        return {cat: list(tools.keys()) for cat, tools in self._tools.items()}


class DeveloperAgent(DeveloperAgentBase):
    """Developer Agent with tool integration framework."""
    
    def __init__(self, state_manager: 'StateManager'):
        super().__init__(state_manager)
        self.tool_registry = ToolRegistry()
        self._setup_event_handlers()
    
    def _setup_event_handlers(self) -> None:
        """Set up event handlers for developer-specific events."""
        self.register_event_handler(EventType.TASK_COMPLETED, self._handle_task_completion)
        self.register_event_handler(EventType.DEPLOYMENT_READY, self._handle_deployment_ready)
    
    async def _execute_task_impl(self, task: Task) -> Dict[str, Any]:
        """Execute developer-specific tasks."""
        self.logger.info(f"Executing developer task: {task.type}")
        
        try:
            if task.type == TaskType.CODE_GENERATION:
                return await self._handle_code_generation_task(task)
            elif task.type == TaskType.REPOSITORY_SETUP:
                return await self._handle_repository_setup_task(task)
            elif task.type == TaskType.DEPLOYMENT:
                return await self._handle_deployment_task(task)
            else:
                raise ValueError(f"Unsupported task type: {task.type}")
        
        except Exception as e:
            self.logger.error(f"Task execution failed: {str(e)}")
            raise
    
    async def _handle_code_generation_task(self, task: Task) -> Dict[str, Any]:
        """Handle code generation tasks."""
        metadata = task.metadata or {}
        template = metadata.get("template", "react-vite")
        specs = metadata.get("specs", {})
        
        code_gen_tool = self.tool_registry.get_tool("code_generation")
        
        if metadata.get("generate_structure", True):
            project_structure = await code_gen_tool.generate_project_structure(template, specs)
            result = {"project_structure": project_structure}
        else:
            component_specs = ComponentSpecs(**specs)
            code_files = await code_gen_tool.generate_component(component_specs)
            result = {"code_files": code_files}
        
        return result
    
    async def _handle_repository_setup_task(self, task: Task) -> Dict[str, Any]:
        """Handle repository setup tasks."""
        metadata = task.metadata or {}
        project_path = metadata.get("project_path", ".")
        remote_url = metadata.get("remote_url")
        
        git_tool = self.tool_registry.get_tool("git")
        repository = await git_tool.initialize_repository(project_path, remote_url)
        
        # Initial commit
        commit_hash = await git_tool.commit_changes(
            repository, 
            "Initial commit: Project structure setup"
        )
        
        return {
            "repository": repository,
            "initial_commit": commit_hash
        }
    
    async def _handle_deployment_task(self, task: Task) -> Dict[str, Any]:
        """Handle deployment tasks."""
        metadata = task.metadata or {}
        config = DeploymentConfig(**metadata.get("config", {}))
        
        deployment_tool = self.tool_registry.get_tool("deployment")
        deployment_result = await deployment_tool.deploy_application(config)
        
        return {"deployment_result": deployment_result}
    
    async def _handle_task_completion(self, event) -> None:
        """Handle task completion events from other agents."""
        payload = event.payload
        task_id = payload.get("task_id")
        
        self.logger.info(f"Received task completion notification for: {task_id}")
        
        # Check if this completion triggers any developer tasks
        # This is where we'd implement workflow coordination logic
        pass
    
    async def _handle_deployment_ready(self, event) -> None:
        """Handle deployment ready events."""
        payload = event.payload
        project_id = payload.get("project_id")
        
        self.logger.info(f"Deployment ready for project: {project_id}")
        
        # Trigger deployment process
        await self.publish_event(EventType.DEPLOYMENT_READY, {
            "project_id": project_id,
            "ready_for_deployment": True
        })
    
    # Public API methods for tool management
    
    def register_code_generation_tool(self, name: str, tool: CodeGenerationTool) -> None:
        """Register a code generation tool."""
        self.tool_registry.register_tool("code_generation", name, tool)
    
    def register_git_tool(self, name: str, tool: GitTool) -> None:
        """Register a Git tool."""
        self.tool_registry.register_tool("git", name, tool)
    
    def register_deployment_tool(self, name: str, tool: DeploymentTool) -> None:
        """Register a deployment tool."""
        self.tool_registry.register_tool("deployment", name, tool)
    
    def set_default_tools(self, code_gen: str = None, git: str = None, deployment: str = None) -> None:
        """Set default tools for each category."""
        if code_gen:
            self.tool_registry.set_default_tool("code_generation", code_gen)
        if git:
            self.tool_registry.set_default_tool("git", git)
        if deployment:
            self.tool_registry.set_default_tool("deployment", deployment)
    
    async def generate_project_structure(self, template: str, specs: Dict[str, Any]) -> ProjectStructure:
        """Generate project structure using the configured code generation tool."""
        tool = self.tool_registry.get_tool("code_generation")
        return await tool.generate_project_structure(template, specs)
    
    async def setup_repository(self, project_path: str, remote_url: Optional[str] = None) -> Repository:
        """Set up Git repository using the configured Git tool."""
        tool = self.tool_registry.get_tool("git")
        return await tool.initialize_repository(project_path, remote_url)
    
    async def deploy_application(self, config: DeploymentConfig) -> DeploymentResult:
        """Deploy application using the configured deployment tool."""
        tool = self.tool_registry.get_tool("deployment")
        return await tool.deploy_application(config)