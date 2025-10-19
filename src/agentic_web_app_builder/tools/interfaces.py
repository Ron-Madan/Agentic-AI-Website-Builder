"""Tool interfaces for the developer agent."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from ..core.interfaces import ToolInterface
from ..models.project import (
    ProjectStructure, ComponentSpecs, CodeFiles, Repository, 
    DeploymentConfig, DeploymentResult
)


class CodeGenerationTool(ToolInterface):
    """Abstract interface for code generation tools."""
    
    @abstractmethod
    async def generate_project_structure(self, template: str, specs: Dict[str, Any]) -> ProjectStructure:
        """Generate project structure from template."""
        pass
    
    @abstractmethod
    async def generate_component(self, component_spec: ComponentSpecs) -> CodeFiles:
        """Generate code components from specifications."""
        pass
    
    @abstractmethod
    async def customize_template(self, template: str, customizations: Dict[str, Any]) -> str:
        """Apply customizations to a template."""
        pass
    
    async def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a code generation command."""
        if command == "generate_project":
            template = parameters.get("template", "react-vite")
            specs = parameters.get("specs", {})
            result = await self.generate_project_structure(template, specs)
            return {"project_structure": result.dict()}
        
        elif command == "generate_component":
            component_spec = ComponentSpecs(**parameters.get("component_spec", {}))
            result = await self.generate_component(component_spec)
            return {"code_files": result.dict()}
        
        elif command == "customize_template":
            template = parameters.get("template", "")
            customizations = parameters.get("customizations", {})
            result = await self.customize_template(template, customizations)
            return {"customized_template": result}
        
        else:
            raise ValueError(f"Unknown code generation command: {command}")
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """Validate code generation parameters."""
        required_keys = {"template", "specs"}
        return all(key in parameters for key in required_keys)


class GitTool(ToolInterface):
    """Abstract interface for Git operations."""
    
    @abstractmethod
    async def initialize_repository(self, project_path: str, remote_url: Optional[str] = None) -> Repository:
        """Initialize a new Git repository."""
        pass
    
    @abstractmethod
    async def commit_changes(self, repository: Repository, message: str, files: List[str] = None) -> str:
        """Commit changes to the repository."""
        pass
    
    @abstractmethod
    async def create_branch(self, repository: Repository, branch_name: str) -> str:
        """Create a new branch."""
        pass
    
    @abstractmethod
    async def merge_branch(self, repository: Repository, source_branch: str, target_branch: str) -> bool:
        """Merge branches with conflict resolution."""
        pass
    
    @abstractmethod
    async def push_changes(self, repository: Repository, branch: str = "main") -> bool:
        """Push changes to remote repository."""
        pass
    
    async def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a Git command."""
        if command == "init":
            project_path = parameters.get("project_path", ".")
            remote_url = parameters.get("remote_url")
            result = await self.initialize_repository(project_path, remote_url)
            return {"repository": result.dict()}
        
        elif command == "commit":
            repository = Repository(**parameters.get("repository", {}))
            message = parameters.get("message", "Automated commit")
            files = parameters.get("files")
            commit_hash = await self.commit_changes(repository, message, files)
            return {"commit_hash": commit_hash}
        
        elif command == "create_branch":
            repository = Repository(**parameters.get("repository", {}))
            branch_name = parameters.get("branch_name")
            branch = await self.create_branch(repository, branch_name)
            return {"branch": branch}
        
        elif command == "merge":
            repository = Repository(**parameters.get("repository", {}))
            source_branch = parameters.get("source_branch")
            target_branch = parameters.get("target_branch")
            success = await self.merge_branch(repository, source_branch, target_branch)
            return {"merge_success": success}
        
        elif command == "push":
            repository = Repository(**parameters.get("repository", {}))
            branch = parameters.get("branch", "main")
            success = await self.push_changes(repository, branch)
            return {"push_success": success}
        
        else:
            raise ValueError(f"Unknown Git command: {command}")
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """Validate Git operation parameters."""
        # Basic validation - specific commands may need additional validation
        return isinstance(parameters, dict)


class DeploymentTool(ToolInterface):
    """Abstract interface for deployment operations."""
    
    @abstractmethod
    async def deploy_application(self, config: DeploymentConfig) -> DeploymentResult:
        """Deploy application to target platform."""
        pass
    
    @abstractmethod
    async def get_deployment_status(self, deployment_id: str) -> Dict[str, Any]:
        """Get current deployment status."""
        pass
    
    @abstractmethod
    async def rollback_deployment(self, deployment_id: str, target_version: str) -> DeploymentResult:
        """Rollback deployment to previous version."""
        pass
    
    @abstractmethod
    async def configure_environment(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Configure deployment environment."""
        pass
    
    async def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a deployment command."""
        if command == "deploy":
            config = DeploymentConfig(**parameters.get("config", {}))
            result = await self.deploy_application(config)
            return {"deployment_result": result.dict()}
        
        elif command == "status":
            deployment_id = parameters.get("deployment_id")
            status = await self.get_deployment_status(deployment_id)
            return {"status": status}
        
        elif command == "rollback":
            deployment_id = parameters.get("deployment_id")
            target_version = parameters.get("target_version")
            result = await self.rollback_deployment(deployment_id, target_version)
            return {"rollback_result": result.dict()}
        
        elif command == "configure":
            config = parameters.get("config", {})
            result = await self.configure_environment(config)
            return {"configuration": result}
        
        else:
            raise ValueError(f"Unknown deployment command: {command}")
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """Validate deployment parameters."""
        required_keys = {"platform", "project_path"}
        config = parameters.get("config", {})
        return all(key in config for key in required_keys)