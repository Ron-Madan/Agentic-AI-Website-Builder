"""Factory for creating and configuring Developer Agent with tools."""

import logging
from typing import Optional

from .developer import DeveloperAgent
from ..tools.code_generation import LLMCodeGenerationTool
from ..tools.git_operations import GitCLITool
from ..tools.deployment import NetlifyDeploymentTool, VercelDeploymentTool, DeploymentManager
from ..tools.llm_service import LLMService
from ..core.state_manager import StateManager


logger = logging.getLogger(__name__)


class DeveloperAgentFactory:
    """Factory for creating configured Developer Agent instances."""
    
    @staticmethod
    def create_developer_agent(
        state_manager: StateManager,
        llm_service: Optional[LLMService] = None,
        netlify_token: Optional[str] = None,
        vercel_token: Optional[str] = None
    ) -> DeveloperAgent:
        """Create a fully configured Developer Agent with all tools."""
        
        # Create the developer agent
        agent = DeveloperAgent(state_manager)
        
        # Initialize and register code generation tool
        code_gen_tool = LLMCodeGenerationTool(llm_service)
        agent.register_code_generation_tool("llm_codegen", code_gen_tool)
        agent.tool_registry.set_default_tool("code_generation", "llm_codegen")
        
        # Initialize and register Git tool
        git_tool = GitCLITool()
        agent.register_git_tool("git_cli", git_tool)
        agent.tool_registry.set_default_tool("git", "git_cli")
        
        # Initialize and register deployment tools
        netlify_tool = NetlifyDeploymentTool(netlify_token)
        vercel_tool = VercelDeploymentTool(vercel_token)
        
        agent.register_deployment_tool("netlify", netlify_tool)
        agent.register_deployment_tool("vercel", vercel_tool)
        
        # Set default deployment tool (prefer Netlify)
        agent.tool_registry.set_default_tool("deployment", "netlify")
        
        logger.info("Developer Agent created with all tools configured")
        return agent
    
    @staticmethod
    def create_minimal_developer_agent(state_manager: StateManager) -> DeveloperAgent:
        """Create a minimal Developer Agent with basic tools only."""
        
        agent = DeveloperAgent(state_manager)
        
        # Only register essential tools
        code_gen_tool = LLMCodeGenerationTool()
        git_tool = GitCLITool()
        
        agent.register_code_generation_tool("llm_codegen", code_gen_tool)
        agent.register_git_tool("git_cli", git_tool)
        
        agent.tool_registry.set_default_tool("code_generation", "llm_codegen")
        agent.tool_registry.set_default_tool("git", "git_cli")
        
        logger.info("Minimal Developer Agent created")
        return agent
    
    @staticmethod
    def create_deployment_manager() -> DeploymentManager:
        """Create a standalone deployment manager."""
        return DeploymentManager()