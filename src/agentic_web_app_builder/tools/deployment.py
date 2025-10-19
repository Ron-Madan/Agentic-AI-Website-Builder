"""Deployment integration tools for Netlify and Vercel."""

import asyncio
import json
import logging
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import aiohttp
import aiofiles

from ..tools.interfaces import DeploymentTool
from ..models.project import DeploymentConfig, DeploymentResult
from ..core.config import get_settings


logger = logging.getLogger(__name__)


class NetlifyDeploymentTool(DeploymentTool):
    """Netlify deployment integration using Netlify API."""
    
    def __init__(self, api_token: Optional[str] = None):
        self.settings = get_settings()
        self.api_token = api_token or getattr(self.settings, 'netlify_api_token', None)
        self.base_url = "https://api.netlify.com/api/v1"
        
        if not self.api_token:
            logger.warning("Netlify API token not configured")
    
    async def deploy_application(self, config: DeploymentConfig) -> DeploymentResult:
        """Deploy application to Netlify."""
        if not self.api_token:
            raise RuntimeError("Netlify API token not configured")
        
        try:
            # Build the application if build command is specified
            if config.build_command:
                await self._run_build_command(config)
            
            # Create deployment package
            deployment_package = await self._create_deployment_package(config)
            
            # Deploy to Netlify
            deployment_result = await self._deploy_to_netlify(config, deployment_package)
            
            # Clean up temporary files
            if os.path.exists(deployment_package):
                os.remove(deployment_package)
            
            return deployment_result
            
        except Exception as e:
            logger.error(f"Netlify deployment failed: {e}")
            raise
    
    async def _run_build_command(self, config: DeploymentConfig) -> None:
        """Run the build command for the project."""
        logger.info(f"Running build command: {config.build_command}")
        
        process = await asyncio.create_subprocess_shell(
            config.build_command,
            cwd=config.project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = f"Build failed: {stderr.decode()}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        logger.info("Build completed successfully")
    
    async def _create_deployment_package(self, config: DeploymentConfig) -> str:
        """Create a zip package for deployment."""
        output_dir = config.output_directory or "dist"
        build_path = os.path.join(config.project_path, output_dir)
        
        if not os.path.exists(build_path):
            raise RuntimeError(f"Build output directory not found: {build_path}")
        
        # Create temporary zip file
        zip_path = os.path.join(config.project_path, "deployment.zip")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(build_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, build_path)
                    zipf.write(file_path, arcname)
        
        logger.info(f"Created deployment package: {zip_path}")
        return zip_path
    
    async def _deploy_to_netlify(self, config: DeploymentConfig, package_path: str) -> DeploymentResult:
        """Deploy package to Netlify."""
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/zip"
        }
        
        # Create site if domain is specified
        site_id = None
        if config.domain:
            site_id = await self._create_or_get_site(config.domain)
        
        async with aiohttp.ClientSession() as session:
            # Read deployment package
            async with aiofiles.open(package_path, 'rb') as f:
                package_data = await f.read()
            
            # Deploy to Netlify
            deploy_url = f"{self.base_url}/sites"
            if site_id:
                deploy_url = f"{self.base_url}/sites/{site_id}/deploys"
            
            async with session.post(deploy_url, headers=headers, data=package_data) as response:
                if response.status not in [200, 201]:
                    error_text = await response.text()
                    raise RuntimeError(f"Netlify deployment failed: {error_text}")
                
                deploy_data = await response.json()
                
                # Wait for deployment to complete
                deployment_id = deploy_data["id"]
                site_url = deploy_data.get("ssl_url") or deploy_data.get("url")
                
                await self._wait_for_deployment(session, deployment_id)
                
                return DeploymentResult(
                    deployment_id=deployment_id,
                    url=site_url,
                    status="ready",
                    build_logs=[],
                    deployed_at=datetime.utcnow(),
                    platform="netlify",
                    version=deploy_data.get("commit_ref")
                )
    
    async def _create_or_get_site(self, domain: str) -> str:
        """Create or get existing Netlify site."""
        headers = {"Authorization": f"Bearer {self.api_token}"}
        
        async with aiohttp.ClientSession() as session:
            # Check if site exists
            async with session.get(f"{self.base_url}/sites", headers=headers) as response:
                if response.status == 200:
                    sites = await response.json()
                    for site in sites:
                        if site.get("custom_domain") == domain or domain in site.get("domain_aliases", []):
                            return site["id"]
            
            # Create new site
            site_data = {"name": domain.replace(".", "-")}
            async with session.post(f"{self.base_url}/sites", headers=headers, json=site_data) as response:
                if response.status == 201:
                    site = await response.json()
                    return site["id"]
                else:
                    raise RuntimeError(f"Failed to create Netlify site: {await response.text()}")
    
    async def _wait_for_deployment(self, session: aiohttp.ClientSession, deployment_id: str) -> None:
        """Wait for deployment to complete."""
        headers = {"Authorization": f"Bearer {self.api_token}"}
        max_attempts = 30
        attempt = 0
        
        while attempt < max_attempts:
            async with session.get(f"{self.base_url}/deploys/{deployment_id}", headers=headers) as response:
                if response.status == 200:
                    deploy_data = await response.json()
                    state = deploy_data.get("state")
                    
                    if state == "ready":
                        logger.info("Deployment completed successfully")
                        return
                    elif state in ["error", "failed"]:
                        raise RuntimeError(f"Deployment failed with state: {state}")
                    
                    # Wait before next check
                    await asyncio.sleep(10)
                    attempt += 1
                else:
                    raise RuntimeError(f"Failed to check deployment status: {await response.text()}")
        
        raise RuntimeError("Deployment timeout - took too long to complete")
    
    async def get_deployment_status(self, deployment_id: str) -> Dict[str, Any]:
        """Get current deployment status."""
        if not self.api_token:
            raise RuntimeError("Netlify API token not configured")
        
        headers = {"Authorization": f"Bearer {self.api_token}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/deploys/{deployment_id}", headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise RuntimeError(f"Failed to get deployment status: {await response.text()}")
    
    async def rollback_deployment(self, deployment_id: str, target_version: str) -> DeploymentResult:
        """Rollback deployment to previous version."""
        # Netlify doesn't have direct rollback, but we can redeploy a previous version
        # This is a simplified implementation
        raise NotImplementedError("Netlify rollback not implemented yet")
    
    async def configure_environment(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Configure deployment environment."""
        # This would configure environment variables, build settings, etc.
        return {"status": "configured", "config": config}


class VercelDeploymentTool(DeploymentTool):
    """Vercel deployment integration using Vercel API."""
    
    def __init__(self, api_token: Optional[str] = None):
        self.settings = get_settings()
        self.api_token = api_token or getattr(self.settings, 'vercel_api_token', None)
        self.base_url = "https://api.vercel.com"
        
        if not self.api_token:
            logger.warning("Vercel API token not configured")
    
    async def deploy_application(self, config: DeploymentConfig) -> DeploymentResult:
        """Deploy application to Vercel."""
        if not self.api_token:
            raise RuntimeError("Vercel API token not configured")
        
        try:
            # Build the application if build command is specified
            if config.build_command:
                await self._run_build_command(config)
            
            # Deploy to Vercel
            deployment_result = await self._deploy_to_vercel(config)
            
            return deployment_result
            
        except Exception as e:
            logger.error(f"Vercel deployment failed: {e}")
            raise
    
    async def _run_build_command(self, config: DeploymentConfig) -> None:
        """Run the build command for the project."""
        logger.info(f"Running build command: {config.build_command}")
        
        process = await asyncio.create_subprocess_shell(
            config.build_command,
            cwd=config.project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = f"Build failed: {stderr.decode()}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        logger.info("Build completed successfully")
    
    async def _deploy_to_vercel(self, config: DeploymentConfig) -> DeploymentResult:
        """Deploy to Vercel using their API."""
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        # Prepare deployment data
        deployment_data = {
            "name": os.path.basename(config.project_path),
            "files": await self._prepare_files(config),
            "projectSettings": {
                "buildCommand": config.build_command,
                "outputDirectory": config.output_directory or "dist"
            }
        }
        
        if config.environment_variables:
            deployment_data["env"] = config.environment_variables
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/v13/deployments", headers=headers, json=deployment_data) as response:
                if response.status not in [200, 201]:
                    error_text = await response.text()
                    raise RuntimeError(f"Vercel deployment failed: {error_text}")
                
                deploy_data = await response.json()
                
                # Wait for deployment to complete
                deployment_id = deploy_data["id"]
                deployment_url = f"https://{deploy_data['url']}"
                
                await self._wait_for_vercel_deployment(session, deployment_id)
                
                return DeploymentResult(
                    deployment_id=deployment_id,
                    url=deployment_url,
                    status="ready",
                    build_logs=[],
                    deployed_at=datetime.utcnow(),
                    platform="vercel",
                    version=deploy_data.get("meta", {}).get("githubCommitSha")
                )
    
    async def _prepare_files(self, config: DeploymentConfig) -> List[Dict[str, Any]]:
        """Prepare files for Vercel deployment."""
        files = []
        project_path = Path(config.project_path)
        
        # Include common web files
        patterns = ["*.html", "*.js", "*.css", "*.json", "*.md", "*.txt"]
        
        for pattern in patterns:
            for file_path in project_path.rglob(pattern):
                if file_path.is_file() and not any(part.startswith('.') for part in file_path.parts):
                    relative_path = file_path.relative_to(project_path)
                    
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                    
                    files.append({
                        "file": str(relative_path),
                        "data": content
                    })
        
        return files
    
    async def _wait_for_vercel_deployment(self, session: aiohttp.ClientSession, deployment_id: str) -> None:
        """Wait for Vercel deployment to complete."""
        headers = {"Authorization": f"Bearer {self.api_token}"}
        max_attempts = 30
        attempt = 0
        
        while attempt < max_attempts:
            async with session.get(f"{self.base_url}/v13/deployments/{deployment_id}", headers=headers) as response:
                if response.status == 200:
                    deploy_data = await response.json()
                    state = deploy_data.get("readyState")
                    
                    if state == "READY":
                        logger.info("Vercel deployment completed successfully")
                        return
                    elif state in ["ERROR", "CANCELED"]:
                        raise RuntimeError(f"Deployment failed with state: {state}")
                    
                    # Wait before next check
                    await asyncio.sleep(10)
                    attempt += 1
                else:
                    raise RuntimeError(f"Failed to check deployment status: {await response.text()}")
        
        raise RuntimeError("Deployment timeout - took too long to complete")
    
    async def get_deployment_status(self, deployment_id: str) -> Dict[str, Any]:
        """Get current deployment status."""
        if not self.api_token:
            raise RuntimeError("Vercel API token not configured")
        
        headers = {"Authorization": f"Bearer {self.api_token}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/v13/deployments/{deployment_id}", headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise RuntimeError(f"Failed to get deployment status: {await response.text()}")
    
    async def rollback_deployment(self, deployment_id: str, target_version: str) -> DeploymentResult:
        """Rollback deployment to previous version."""
        # Vercel doesn't have direct rollback, but we can promote a previous deployment
        raise NotImplementedError("Vercel rollback not implemented yet")
    
    async def configure_environment(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Configure deployment environment."""
        return {"status": "configured", "config": config}


class DeploymentManager:
    """Manager for different deployment tools."""
    
    def __init__(self):
        self.tools = {
            "netlify": NetlifyDeploymentTool(),
            "vercel": VercelDeploymentTool()
        }
    
    def get_tool(self, platform: str) -> DeploymentTool:
        """Get deployment tool for platform."""
        if platform not in self.tools:
            raise ValueError(f"Unsupported deployment platform: {platform}")
        return self.tools[platform]
    
    async def deploy(self, config: DeploymentConfig) -> DeploymentResult:
        """Deploy using the appropriate tool."""
        tool = self.get_tool(config.platform)
        return await tool.deploy_application(config)
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """Validate deployment parameters."""
        required_keys = {"platform", "project_path"}
        config = parameters.get("config", {})
        return all(key in config for key in required_keys)
    
    async def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute deployment command."""
        if command == "deploy":
            config = DeploymentConfig(**parameters.get("config", {}))
            result = await self.deploy(config)
            return {"deployment_result": result.dict()}
        
        elif command == "status":
            platform = parameters.get("platform")
            deployment_id = parameters.get("deployment_id")
            tool = self.get_tool(platform)
            status = await tool.get_deployment_status(deployment_id)
            return {"status": status}
        
        elif command == "rollback":
            platform = parameters.get("platform")
            deployment_id = parameters.get("deployment_id")
            target_version = parameters.get("target_version")
            tool = self.get_tool(platform)
            result = await tool.rollback_deployment(deployment_id, target_version)
            return {"rollback_result": result.dict()}
        
        elif command == "configure":
            platform = parameters.get("platform")
            config = parameters.get("config", {})
            tool = self.get_tool(platform)
            result = await tool.configure_environment(config)
            return {"configuration": result}
        
        else:
            raise ValueError(f"Unknown deployment command: {command}")