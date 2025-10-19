"""LLM service for integrating with OpenAI and Anthropic APIs."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Union
from enum import Enum

import openai
import anthropic
from pydantic import BaseModel, Field

from ..core.config import get_settings
from ..core.interfaces import ToolInterface


logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class LLMMessage(BaseModel):
    """Message for LLM conversation."""
    role: str = Field(..., description="Message role (system, user, assistant)")
    content: str = Field(..., description="Message content")


class LLMRequest(BaseModel):
    """Request to LLM service."""
    messages: List[LLMMessage] = Field(..., description="Conversation messages")
    model: Optional[str] = Field(None, description="Model to use (overrides default)")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens to generate")
    temperature: Optional[float] = Field(None, description="Temperature for generation")
    provider: Optional[LLMProvider] = Field(None, description="LLM provider to use")


class LLMResponse(BaseModel):
    """Response from LLM service."""
    content: str = Field(..., description="Generated content")
    model: str = Field(..., description="Model used for generation")
    provider: LLMProvider = Field(..., description="Provider used")
    usage: Dict[str, Any] = Field(default_factory=dict, description="Token usage information")


class LLMService(ToolInterface):
    """Service for interacting with LLM providers."""
    
    def __init__(self):
        self.settings = get_settings()
        self._openai_client: Optional[openai.AsyncOpenAI] = None
        self._anthropic_client: Optional[anthropic.AsyncAnthropic] = None
        self._initialize_clients()
    
    def _initialize_clients(self) -> None:
        """Initialize LLM provider clients."""
        # Initialize OpenAI client
        if hasattr(self.settings, 'llm_openai_api_key') and self.settings.llm_openai_api_key:
            self._openai_client = openai.AsyncOpenAI(
                api_key=self.settings.llm_openai_api_key
            )
            logger.info("OpenAI client initialized")
        
        # Initialize Anthropic client
        if hasattr(self.settings, 'llm_anthropic_api_key') and self.settings.llm_anthropic_api_key:
            self._anthropic_client = anthropic.AsyncAnthropic(
                api_key=self.settings.llm_anthropic_api_key
            )
            logger.info("Anthropic client initialized")
    
    async def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute LLM command."""
        if command == "generate":
            request = LLMRequest(**parameters)
            response = await self.generate(request)
            return response.dict()
        else:
            raise ValueError(f"Unknown command: {command}")
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """Validate LLM parameters."""
        try:
            LLMRequest(**parameters)
            return True
        except Exception as e:
            logger.error(f"Parameter validation failed: {str(e)}")
            return False
    
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate text using the specified LLM provider."""
        provider = request.provider or self._get_default_provider()
        
        if provider == LLMProvider.OPENAI:
            return await self._generate_openai(request)
        elif provider == LLMProvider.ANTHROPIC:
            return await self._generate_anthropic(request)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    
    async def _generate_openai(self, request: LLMRequest) -> LLMResponse:
        """Generate text using OpenAI API."""
        if not self._openai_client:
            raise RuntimeError("OpenAI client not initialized. Check API key configuration.")
        
        model = request.model or getattr(self.settings, 'default_model', 'gpt-4')
        max_tokens = request.max_tokens or getattr(self.settings, 'max_tokens', 4000)
        temperature = request.temperature or getattr(self.settings, 'temperature', 0.7)
        
        # Convert messages to OpenAI format
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        
        try:
            response = await self._openai_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            return LLMResponse(
                content=response.choices[0].message.content,
                model=model,
                provider=LLMProvider.OPENAI,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            )
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            raise
    
    async def _generate_anthropic(self, request: LLMRequest) -> LLMResponse:
        """Generate text using Anthropic API."""
        if not self._anthropic_client:
            raise RuntimeError("Anthropic client not initialized. Check API key configuration.")
        
        model = request.model or "claude-3-sonnet-20240229"
        max_tokens = request.max_tokens or getattr(self.settings, 'max_tokens', 4000)
        temperature = request.temperature or getattr(self.settings, 'temperature', 0.7)
        
        # Convert messages to Anthropic format
        system_message = None
        messages = []
        
        for msg in request.messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                messages.append({"role": msg.role, "content": msg.content})
        
        try:
            response = await self._anthropic_client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_message,
                messages=messages
            )
            
            return LLMResponse(
                content=response.content[0].text,
                model=model,
                provider=LLMProvider.ANTHROPIC,
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens
                }
            )
        except Exception as e:
            logger.error(f"Anthropic API error: {str(e)}")
            raise
    
    def _get_default_provider(self) -> LLMProvider:
        """Get the default LLM provider based on available API keys."""
        if self._openai_client:
            return LLMProvider.OPENAI
        elif self._anthropic_client:
            return LLMProvider.ANTHROPIC
        else:
            raise RuntimeError("No LLM provider configured. Please set API keys.")
    
    async def analyze_user_requirements(self, description: str, requirements: List[str]) -> Dict[str, Any]:
        """Analyze user requirements and extract structured information."""
        system_prompt = """You are an expert software architect analyzing user requirements for web application development.
        
        Your task is to analyze the user's description and requirements, then extract structured information including:
        1. Project type and framework preferences
        2. Key features and functionality
        3. Technical requirements and constraints
        4. Deployment preferences
        5. Any ambiguities that need clarification
        
        Return your analysis as a JSON object with the following structure:
        {
            "project_type": "portfolio|blog|ecommerce|landing_page|other",
            "framework_preference": "react|svelte|vue|none",
            "key_features": ["feature1", "feature2", ...],
            "technical_requirements": ["requirement1", "requirement2", ...],
            "deployment_platform": "netlify|vercel|github_pages|other",
            "ambiguities": ["question1", "question2", ...],
            "confidence_score": 0.8
        }"""
        
        user_prompt = f"""Please analyze the following web application request:

Description: {description}

Additional Requirements: {', '.join(requirements) if requirements else 'None specified'}

Provide a structured analysis as requested."""
        
        request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt)
            ],
            temperature=0.3  # Lower temperature for more consistent analysis
        )
        
        response = await self.generate(request)
        
        try:
            # Parse JSON response
            analysis = json.loads(response.content)
            return analysis
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response as JSON: {response.content}")
            # Return a basic fallback analysis
            return {
                "project_type": "other",
                "framework_preference": "react",
                "key_features": ["basic_website"],
                "technical_requirements": [],
                "deployment_platform": "netlify",
                "ambiguities": ["Could not parse detailed requirements"],
                "confidence_score": 0.1
            }
    
    async def decompose_into_tasks(self, analysis: Dict[str, Any], description: str) -> List[Dict[str, Any]]:
        """Decompose project requirements into specific tasks."""
        system_prompt = """You are an expert project manager breaking down web development projects into specific, actionable tasks.
        
        Based on the project analysis, create a detailed task breakdown that includes:
        1. Code generation tasks
        2. Repository setup tasks
        3. Testing tasks
        4. Deployment tasks
        5. Monitoring setup tasks
        
        Each task should have:
        - A clear, specific description
        - Estimated duration in minutes
        - Dependencies on other tasks
        - The type of task (code_generation, repository_setup, testing, deployment, monitoring_setup)
        
        Return the tasks as a JSON array with this structure:
        [
            {
                "id": "task_1",
                "type": "code_generation",
                "description": "Generate React components for homepage",
                "estimated_duration_minutes": 30,
                "dependencies": [],
                "agent_assigned": "developer"
            },
            ...
        ]"""
        
        user_prompt = f"""Based on this project analysis, create a detailed task breakdown:

Project Analysis:
{json.dumps(analysis, indent=2)}

Original Description: {description}

Please provide a comprehensive task list that covers all aspects of building and deploying this web application."""
        
        request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt)
            ],
            temperature=0.4
        )
        
        response = await self.generate(request)
        
        try:
            tasks = json.loads(response.content)
            return tasks if isinstance(tasks, list) else []
        except json.JSONDecodeError:
            logger.error(f"Failed to parse task breakdown as JSON: {response.content}")
            # Return basic fallback tasks
            return [
                {
                    "id": "task_1",
                    "type": "code_generation",
                    "description": "Generate basic web application structure",
                    "estimated_duration_minutes": 60,
                    "dependencies": [],
                    "agent_assigned": "developer"
                },
                {
                    "id": "task_2",
                    "type": "deployment",
                    "description": "Deploy application to hosting platform",
                    "estimated_duration_minutes": 15,
                    "dependencies": ["task_1"],
                    "agent_assigned": "developer"
                }
            ]