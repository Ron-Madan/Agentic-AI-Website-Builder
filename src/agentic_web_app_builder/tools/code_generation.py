"""LLM-based code generation tool implementation."""

import json
import logging
import os
from typing import Dict, Any, List, Optional
from pathlib import Path

from ..tools.interfaces import CodeGenerationTool
from ..tools.llm_service import LLMService, LLMRequest, LLMMessage
from ..models.project import ProjectStructure, ComponentSpecs, CodeFiles


logger = logging.getLogger(__name__)


class LLMCodeGenerationTool(CodeGenerationTool):
    """LLM-based code generation tool using OpenAI/Anthropic APIs."""
    
    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm_service = llm_service or LLMService()
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, Dict[str, Any]]:
        """Load project templates configuration."""
        return {
            "react-vite": {
                "name": "React with Vite",
                "description": "Modern React application with Vite build tool",
                "dependencies": {
                    "react": "^18.2.0",
                    "react-dom": "^18.2.0",
                    "vite": "^4.4.5",
                    "@vitejs/plugin-react": "^4.0.3"
                },
                "dev_dependencies": {
                    "@types/react": "^18.2.15",
                    "@types/react-dom": "^18.2.7",
                    "eslint": "^8.45.0",
                    "eslint-plugin-react": "^7.32.2",
                    "eslint-plugin-react-hooks": "^4.6.0",
                    "eslint-plugin-react-refresh": "^0.4.3",
                    "typescript": "^5.0.2"
                },
                "scripts": {
                    "dev": "vite",
                    "build": "tsc && vite build",
                    "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0",
                    "preview": "vite preview"
                },
                "directories": [
                    "src", "src/components", "src/pages", "src/hooks", 
                    "src/utils", "src/styles", "public"
                ],
                "files": [
                    "index.html", "package.json", "tsconfig.json", "vite.config.ts",
                    "src/main.tsx", "src/App.tsx", "src/App.css", "src/index.css"
                ]
            },
            "sveltekit": {
                "name": "SvelteKit",
                "description": "Full-stack Svelte application with SvelteKit",
                "dependencies": {
                    "@sveltejs/adapter-auto": "^2.0.0",
                    "@sveltejs/kit": "^1.20.4",
                    "svelte": "^4.0.5"
                },
                "dev_dependencies": {
                    "@sveltejs/adapter-auto": "^2.0.0",
                    "@sveltejs/kit": "^1.20.4",
                    "svelte": "^4.0.5",
                    "svelte-check": "^3.4.3",
                    "typescript": "^5.0.0",
                    "tslib": "^2.4.1",
                    "vite": "^4.4.2"
                },
                "scripts": {
                    "dev": "vite dev",
                    "build": "vite build",
                    "preview": "vite preview",
                    "check": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json",
                    "check:watch": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json --watch"
                },
                "directories": [
                    "src", "src/lib", "src/routes", "src/app.html", "static"
                ],
                "files": [
                    "package.json", "svelte.config.js", "tsconfig.json", "vite.config.ts",
                    "src/app.html", "src/app.d.ts", "src/routes/+layout.svelte", "src/routes/+page.svelte"
                ]
            }
        }
    
    async def generate_project_structure(self, template: str, specs: Dict[str, Any]) -> ProjectStructure:
        """Generate project structure from template using LLM."""
        if template not in self.templates:
            raise ValueError(f"Unknown template: {template}. Available: {list(self.templates.keys())}")
        
        template_config = self.templates[template]
        project_name = specs.get("name", "my-web-app")
        features = specs.get("features", [])
        styling = specs.get("styling", "css")
        
        # Generate customized project structure using LLM
        system_prompt = f"""You are an expert web developer creating a {template_config['name']} project structure.
        
        Based on the template configuration and user specifications, generate a complete project structure including:
        1. All necessary directories
        2. All required files with their basic content
        3. Updated dependencies if needed for requested features
        4. Appropriate scripts for the project
        
        Template: {template}
        Project Name: {project_name}
        Requested Features: {features}
        Styling Preference: {styling}
        
        Return a JSON object with this exact structure:
        {{
            "name": "{project_name}",
            "template": "{template}",
            "directories": ["dir1", "dir2", ...],
            "files": ["file1", "file2", ...],
            "dependencies": {{"package": "version", ...}},
            "scripts": {{"script": "command", ...}},
            "configuration": {{"key": "value", ...}}
        }}"""
        
        user_prompt = f"""Generate a project structure for:
        
        Project Name: {project_name}
        Template: {template}
        Features: {', '.join(features) if features else 'Basic functionality'}
        Styling: {styling}
        
        Base template configuration:
        {json.dumps(template_config, indent=2)}
        
        Please customize this structure based on the requested features and return the JSON structure."""
        
        request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt)
            ],
            temperature=0.3
        )
        
        response = await self.llm_service.generate(request)
        
        try:
            structure_data = json.loads(response.content)
            return ProjectStructure(**structure_data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse project structure JSON: {e}")
            # Return basic structure as fallback
            return ProjectStructure(
                name=project_name,
                template=template,
                directories=template_config["directories"],
                files=template_config["files"],
                dependencies=template_config["dependencies"],
                scripts=template_config["scripts"],
                configuration={}
            )
    
    async def generate_component(self, component_spec: ComponentSpecs) -> CodeFiles:
        """Generate code components using LLM."""
        system_prompt = """You are an expert frontend developer generating high-quality, production-ready code components.
        
        Based on the component specifications, generate:
        1. The main component file with complete implementation
        2. Associated style files if needed
        3. Type definitions if using TypeScript
        4. Any utility functions or hooks if required
        5. Updated import statements for dependencies
        
        Follow these guidelines:
        - Write clean, readable, and well-documented code
        - Use modern best practices and patterns
        - Include proper TypeScript types if applicable
        - Add appropriate error handling
        - Include accessibility features where relevant
        - Use semantic HTML elements
        
        Return a JSON object with this structure:
        {
            "files": {
                "path/to/file.tsx": "file content here",
                "path/to/styles.css": "css content here",
                ...
            },
            "metadata": {
                "component_type": "functional|class",
                "framework": "react|svelte",
                "typescript": true|false
            },
            "dependencies_added": ["package1", "package2", ...],
            "imports_updated": ["import statement 1", "import statement 2", ...]
        }"""
        
        user_prompt = f"""Generate a {component_spec.component_type} component with these specifications:
        
        Component Name: {component_spec.component_name}
        Type: {component_spec.component_type}
        Props: {json.dumps(component_spec.props, indent=2) if component_spec.props else 'None'}
        Styling: {json.dumps(component_spec.styling, indent=2) if component_spec.styling else 'Basic CSS'}
        Functionality: {', '.join(component_spec.functionality) if component_spec.functionality else 'Basic display'}
        Dependencies: {', '.join(component_spec.dependencies) if component_spec.dependencies else 'None'}
        
        Please generate complete, production-ready code for this component."""
        
        request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt)
            ],
            temperature=0.4
        )
        
        response = await self.llm_service.generate(request)
        
        try:
            code_data = json.loads(response.content)
            return CodeFiles(**code_data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse component code JSON: {e}")
            # Return basic fallback component
            component_name = component_spec.component_name
            file_extension = ".tsx" if "react" in component_spec.component_type.lower() else ".svelte"
            
            basic_component = f"""// {component_name} Component
import React from 'react';

interface {component_name}Props {{
  // Add props here
}}

const {component_name}: React.FC<{component_name}Props> = (props) => {{
  return (
    <div className="{component_name.lower()}">
      <h1>{component_name}</h1>
      <p>Component generated successfully!</p>
    </div>
  );
}};

export default {component_name};"""
            
            return CodeFiles(
                files={f"src/components/{component_name}{file_extension}": basic_component},
                metadata={"component_type": "functional", "framework": "react", "typescript": True},
                dependencies_added=[],
                imports_updated=[]
            )
    
    async def customize_template(self, template: str, customizations: Dict[str, Any]) -> str:
        """Apply customizations to a template using LLM."""
        system_prompt = """You are an expert web developer customizing project templates.
        
        Apply the requested customizations to the template while maintaining:
        1. Code quality and best practices
        2. Proper project structure
        3. Compatibility with existing dependencies
        4. Performance considerations
        
        Return the customized template configuration as a JSON string."""
        
        user_prompt = f"""Customize this template:
        
        Base Template: {template}
        Customizations: {json.dumps(customizations, indent=2)}
        
        Please apply these customizations and return the updated template configuration."""
        
        request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt)
            ],
            temperature=0.3
        )
        
        response = await self.llm_service.generate(request)
        return response.content
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """Validate code generation parameters."""
        if "template" in parameters:
            return parameters["template"] in self.templates
        elif "component_spec" in parameters:
            try:
                ComponentSpecs(**parameters["component_spec"])
                return True
            except Exception:
                return False
        return False
    
    async def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute code generation command."""
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