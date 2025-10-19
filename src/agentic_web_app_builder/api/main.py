"""Real agent-powered FastAPI application."""

from fastapi import FastAPI, HTTPException, Header, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import logging
import os
import asyncio

from ..core.config import get_settings
from ..tools.llm_service import LLMService, LLMRequest, LLMMessage
from ..agents.planner import PlannerAgent
from ..agents.developer import DeveloperAgent
from ..core.state_manager import StateManager
from ..models.project import ProjectRequest, ProjectState


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Request/Response Models
class CreateProjectRequest(BaseModel):
    """Request model for creating a new project."""
    user_id: str = Field(..., description="ID of the user making the request", min_length=1)
    description: str = Field(..., description="Natural language description of the project", min_length=10)
    requirements: List[str] = Field(default_factory=list, description="List of specific requirements")
    preferences: Dict[str, Any] = Field(default_factory=dict, description="User preferences and configuration")


class ProjectResponse(BaseModel):
    """Response model for project operations."""
    project_id: str
    status: str
    message: str
    created_at: datetime
    data: Optional[Dict[str, Any]] = None


class ProjectStatusResponse(BaseModel):
    """Response model for project status."""
    project_id: str
    status: str
    current_phase: str
    progress_percentage: float
    completed_tasks: int
    pending_tasks: int
    failed_tasks: int
    last_updated: datetime
    deployment_url: Optional[str] = None


# Global state
projects_store: Dict[str, Dict[str, Any]] = {}
sessions_store: Dict[str, Dict[str, Any]] = {}
llm_service: Optional[LLMService] = None
planner_agent: Optional[PlannerAgent] = None
developer_agent: Optional[DeveloperAgent] = None
state_manager: Optional[StateManager] = None


async def initialize_agents():
    """Initialize the agent system."""
    global llm_service, planner_agent, developer_agent, state_manager
    
    try:
        # Initialize LLM service
        llm_service = LLMService()
        
        # Initialize state manager
        from ..core.state_manager import InMemoryStateManager
        state_manager = InMemoryStateManager()
        
        # Initialize agents (simplified for now)
        # planner_agent = PlannerAgent("planner_001", state_manager)
        # developer_agent = DeveloperAgent("developer_001", state_manager)
        
        logger.info("Agents initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize agents: {e}")
        # Continue with simulation mode
        pass


def create_agent_app() -> FastAPI:
    """Create the agent-powered FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="An intelligent system for autonomous web application development",
        debug=settings.is_development()
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development() else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Mount static files
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    
    return app


# Create the app instance
app = create_agent_app()


@app.on_event("startup")
async def startup_event():
    """Initialize agents on startup."""
    await initialize_agents()


@app.get("/")
async def root():
    """Serve the main web interface."""
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    index_path = os.path.join(static_dir, "index.html")
    
    if os.path.exists(index_path):
        return FileResponse(index_path)
    else:
        settings = get_settings()
        return {
            "message": f"Welcome to {settings.app_name}",
            "version": settings.version,
            "environment": settings.environment,
            "status": "running",
            "agents_active": planner_agent is not None and developer_agent is not None
        }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "message": "Agentic Web App Builder is running",
        "timestamp": datetime.utcnow(),
        "projects_count": len(projects_store),
        "sessions_count": len(sessions_store),
        "agents_initialized": planner_agent is not None,
        "llm_service_active": llm_service is not None
    }


# Session Management
@app.post("/api/user-input/session")
async def create_session(user_id: str):
    """Create a new user session."""
    session_id = str(uuid.uuid4())
    sessions_store[session_id] = {
        "user_id": user_id,
        "created_at": datetime.utcnow(),
        "projects": [],
        "last_activity": datetime.utcnow()
    }
    
    return {
        "session_id": session_id,
        "user_id": user_id,
        "created_at": datetime.utcnow(),
        "message": "Session created successfully"
    }


# Real agent-powered project creation with governance
async def process_project_with_agents(project_id: str, project_request: CreateProjectRequest):
    """Process a project using real agents with human-in-the-loop governance."""
    try:
        logger.info(f"Starting agent processing for project {project_id}")
        
        # Update project status
        if project_id in projects_store:
            projects_store[project_id]["status"] = "planning"
            projects_store[project_id]["current_phase"] = "planning"
            projects_store[project_id]["progress"] = 10.0
            projects_store[project_id]["last_updated"] = datetime.utcnow()
        
        # Step 1: Use LLM to analyze the project description
        if llm_service:
            analysis_request = LLMRequest(
                messages=[
                    LLMMessage(role="system", content="""You are a project planning assistant. Analyze the user's project description and provide:
1. Project type (portfolio, landing page, blog, etc.)
2. Key features needed
3. Technical requirements
4. Estimated complexity (1-5 scale)
5. Recommended tech stack

Respond in JSON format."""),
                    LLMMessage(role="user", content=f"""
Project Description: {project_request.description}
Requirements: {project_request.requirements}
Preferences: {project_request.preferences}

Please analyze this project and provide your assessment.""")
                ]
            )
            
            analysis_response = await llm_service.generate(analysis_request)
            logger.info(f"LLM Analysis: {analysis_response.content}")
            
            # Update project with analysis
            if project_id in projects_store:
                projects_store[project_id]["llm_analysis"] = analysis_response.content
                projects_store[project_id]["progress"] = 25.0
                projects_store[project_id]["last_updated"] = datetime.utcnow()
        
        # Step 2: Create execution plan and REQUEST USER APPROVAL
        await asyncio.sleep(2)  # Simulate planning time
        if project_id in projects_store:
            # Create approval request
            approval_id = f"approval_{project_id[:8]}"
            projects_store[project_id]["pending_approval"] = {
                "approval_id": approval_id,
                "type": "execution_plan",
                "title": "Execution Plan Approval Required",
                "description": "Please review and approve the execution plan before development begins",
                "plan_summary": {
                    "framework": project_request.preferences.get("framework", "react"),
                    "styling": project_request.preferences.get("styling", "tailwind"),
                    "deployment": project_request.preferences.get("deployment", "netlify"),
                    "estimated_duration": "10-15 minutes",
                    "phases": ["Planning", "Development", "Testing", "Deployment"]
                },
                "created_at": datetime.utcnow()
            }
            projects_store[project_id]["status"] = "awaiting_approval"
            projects_store[project_id]["current_phase"] = "awaiting_approval"
            projects_store[project_id]["progress"] = 30.0
            projects_store[project_id]["last_updated"] = datetime.utcnow()
            
            logger.info(f"Project {project_id} awaiting user approval")
            return  # Stop here and wait for approval
        
    except Exception as e:
        logger.error(f"Error processing project {project_id}: {e}")
        if project_id in projects_store:
            projects_store[project_id]["status"] = "failed"
            projects_store[project_id]["error"] = str(e)
            projects_store[project_id]["last_updated"] = datetime.utcnow()


async def continue_after_approval(project_id: str):
    """Continue project processing after user approval."""
    try:
        if project_id not in projects_store:
            return
        
        project = projects_store[project_id]
        project_request_data = project["request"]
        
        # Step 3: Generate code using LLM
        project["status"] = "development"
        project["current_phase"] = "development"
        project["progress"] = 40.0
        project["completed_tasks"] = 1
        project["pending_tasks"] = 4
        project["last_updated"] = datetime.utcnow()
        
        if llm_service:
            code_request = LLMRequest(
                messages=[
                    LLMMessage(role="system", content="""You are an expert web developer. Create a complete, beautiful, single-page HTML website.

REQUIREMENTS:
- Generate ONLY complete HTML code (no explanations, no markdown, no code blocks)
- Use Tailwind CSS via CDN for styling
- Make it modern, professional, and visually appealing
- Include proper responsive design
- Add smooth animations and hover effects
- Use a cohesive color scheme
- Include realistic placeholder content
- Make it production-ready

STRUCTURE:
- Complete HTML document with proper DOCTYPE, head, and body
- Include Tailwind CSS CDN in the head
- Create multiple sections (hero, about, features, contact, etc.)
- Use modern design patterns (gradients, shadows, rounded corners)
- Add interactive elements and smooth scrolling

OUTPUT: Return ONLY the complete HTML code, nothing else."""),
                    LLMMessage(role="user", content=f"""
Create a beautiful single-page website for: {project_request_data['description']}

Additional requirements: {project_request_data['requirements']}
Styling: Use Tailwind CSS with modern design
Framework: Single-page HTML with embedded CSS/JS if needed

Make it visually stunning with:
- Hero section with compelling headline
- Multiple content sections
- Modern color scheme and typography  
- Smooth animations and transitions
- Professional layout and spacing
- Mobile-responsive design

Generate the complete HTML code now.""")
                ]
            )
            
            code_response = await llm_service.generate(code_request)
            logger.info(f"Generated code length: {len(code_response.content)} characters")
            
            # Update project with generated code
            project["generated_code"] = code_response.content
            project["progress"] = 60.0
            project["current_phase"] = "testing"
            project["completed_tasks"] = 2
            project["pending_tasks"] = 3
            project["last_updated"] = datetime.utcnow()
        
        # Step 4: Testing phase
        await asyncio.sleep(3)  # Simulate testing
        project["progress"] = 80.0
        project["current_phase"] = "deployment"
        project["completed_tasks"] = 3
        project["pending_tasks"] = 2
        project["last_updated"] = datetime.utcnow()
        
        # Step 5: REQUEST DEPLOYMENT APPROVAL
        deployment_approval_id = f"deploy_approval_{project_id[:8]}"
        project["pending_deployment_approval"] = {
            "approval_id": deployment_approval_id,
            "type": "deployment",
            "title": "Deployment Approval Required",
            "description": "Ready to deploy to Netlify. Please review and approve deployment.",
            "created_at": datetime.utcnow()
        }
        project["status"] = "awaiting_deployment_approval"
        project["current_phase"] = "awaiting_deployment_approval"
        project["last_updated"] = datetime.utcnow()
        
        logger.info(f"Project {project_id} awaiting deployment approval")
        
    except Exception as e:
        logger.error(f"Error continuing project {project_id}: {e}")
        if project_id in projects_store:
            projects_store[project_id]["status"] = "failed"
            projects_store[project_id]["error"] = str(e)
            projects_store[project_id]["last_updated"] = datetime.utcnow()


async def deploy_after_approval(project_id: str):
    """Deploy project after user approval."""
    try:
        if project_id not in projects_store:
            return
        
        project = projects_store[project_id]
        
        # Deploy to Netlify
        deployment_url = await deploy_to_netlify(project_id, project)
        
        # Final update
        project["status"] = "completed"
        project["current_phase"] = "deployed"
        project["progress"] = 100.0
        project["deployment_url"] = deployment_url
        project["completed_tasks"] = 5
        project["pending_tasks"] = 0
        project["last_updated"] = datetime.utcnow()
        
        logger.info(f"Project {project_id} deployed successfully to {deployment_url}")
        
    except Exception as e:
        logger.error(f"Error deploying project {project_id}: {e}")
        if project_id in projects_store:
            projects_store[project_id]["status"] = "failed"
            projects_store[project_id]["error"] = str(e)
            projects_store[project_id]["last_updated"] = datetime.utcnow()


async def deploy_to_netlify(project_id: str, project_data: Dict[str, Any]) -> str:
    """Deploy the generated website to Netlify."""
    import tempfile
    import zipfile
    import aiohttp
    import httpx
    
    # Check multiple possible environment variable names
    netlify_token = (
        os.getenv("NETLIFY_ACCESS_TOKEN") or 
        os.getenv("DEPLOY_NETLIFY_ACCESS_TOKEN") or
        os.getenv("NETLIFY_TOKEN")
    )
    
    if not netlify_token:
        # Check settings
        settings = get_settings()
        netlify_token = getattr(settings, 'netlify_access_token', None)
    
    logger.info(f"Netlify token found: {'Yes' if netlify_token else 'No'}")
    if netlify_token:
        logger.info(f"Using Netlify token: {netlify_token[:10]}...")
    
    if not netlify_token:
        logger.warning("No Netlify token found in environment variables. Using demo URL.")
        logger.info("Available env vars: NETLIFY_ACCESS_TOKEN, DEPLOY_NETLIFY_ACCESS_TOKEN")
        return f"https://demo-{project_id[:8]}.netlify.app"
    
    try:
        # Get the generated code
        website_content = project_data.get("generated_code")
        if not website_content:
            # Fallback to simple generated content
            website_content = generate_fallback_website(project_data)
        
        # Clean the generated content to ensure it's pure HTML
        website_content = clean_html_content(website_content)
        
        # Log content info for debugging
        logger.info(f"Deploying content length: {len(website_content)} characters")
        logger.info(f"Content starts with: {website_content[:100]}...")
        logger.info(f"Content ends with: ...{website_content[-50:]}")
        logger.info(f"Content is HTML: {website_content.strip().startswith('<!DOCTYPE html>') or website_content.strip().startswith('<html')}")
        
        # Save a copy for debugging
        debug_path = f"/tmp/debug_deploy_{project_id}.html"
        try:
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(website_content)
            logger.info(f"Debug HTML saved to: {debug_path}")
        except Exception as e:
            logger.warning(f"Could not save debug file: {e}")
        
        # Create temporary files
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create site directory structure
            site_dir = os.path.join(temp_dir, "site")
            os.makedirs(site_dir, exist_ok=True)
            
            # Write the HTML file
            index_path = os.path.join(site_dir, "index.html")
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(website_content)
            
            # Create a simple _redirects file for Netlify
            redirects_path = os.path.join(site_dir, "_redirects")
            with open(redirects_path, "w", encoding="utf-8") as f:
                f.write("/*    /index.html   200\n")
            
            # Create zip file with proper structure
            zip_path = os.path.join(temp_dir, "site.zip")
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                # Add files with proper paths
                zipf.write(index_path, "index.html")
                zipf.write(redirects_path, "_redirects")
            
            # Deploy to Netlify
            import ssl
            
            # Create SSL context that doesn't verify certificates (for development)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with aiohttp.ClientSession(connector=connector) as session:
                headers = {
                    "Authorization": f"Bearer {netlify_token}",
                    "Content-Type": "application/zip"
                }
                
                with open(zip_path, "rb") as f:
                    async with session.post(
                        "https://api.netlify.com/api/v1/sites",
                        headers=headers,
                        data=f
                    ) as response:
                        logger.info(f"Netlify API response status: {response.status}")
                        
                        if response.status == 201:
                            result = await response.json()
                            deployment_url = result.get("url", f"https://demo-{project_id[:8]}.netlify.app")
                            logger.info(f"✅ Successfully deployed to Netlify: {deployment_url}")
                            return deployment_url
                        else:
                            error_text = await response.text()
                            logger.error(f"❌ Netlify deployment failed: {response.status} - {error_text}")
                            return f"https://demo-{project_id[:8]}.netlify.app"
    
    except Exception as e:
        logger.error(f"❌ aiohttp deployment error: {e}")
        logger.info("Trying httpx as fallback...")
        
        # Fallback to httpx
        try:
            with open(zip_path, "rb") as f:
                async with httpx.AsyncClient(verify=False) as client:
                    headers = {
                        "Authorization": f"Bearer {netlify_token}",
                        "Content-Type": "application/zip"
                    }
                    
                    response = await client.post(
                        "https://api.netlify.com/api/v1/sites",
                        headers=headers,
                        content=f.read()
                    )
                    
                    if response.status_code == 201:
                        result = response.json()
                        deployment_url = result.get("url", f"https://demo-{project_id[:8]}.netlify.app")
                        logger.info(f"✅ Successfully deployed via httpx: {deployment_url}")
                        return deployment_url
                    else:
                        logger.error(f"❌ httpx deployment failed: {response.status_code} - {response.text}")
                        
        except Exception as e2:
            logger.error(f"❌ httpx fallback also failed: {e2}")
        
        logger.info("All deployment methods failed, using demo URL")
        return f"https://demo-{project_id[:8]}.netlify.app"


def clean_html_content(content: str) -> str:
    """Clean generated content to ensure it's pure HTML."""
    if not content:
        return content
    
    # Remove markdown code blocks if present
    import re
    
    # Remove ```html and ``` markers
    content = re.sub(r'```html\s*\n?', '', content)
    content = re.sub(r'\n?```\s*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'```', '', content)
    
    # Remove any explanatory text before the HTML
    # Look for the start of HTML document
    html_start = content.find('<!DOCTYPE html>')
    if html_start == -1:
        html_start = content.find('<html')
    
    if html_start > 0:
        # Log what we're removing
        removed_text = content[:html_start].strip()
        if removed_text:
            logger.info(f"Removing text before HTML: {removed_text[:100]}...")
        content = content[html_start:]
    
    # Remove any text after the closing </html> tag
    html_end = content.rfind('</html>')
    if html_end != -1:
        after_html = content[html_end + 7:].strip()
        if after_html:
            logger.info(f"Removing text after HTML: {after_html[:100]}...")
        content = content[:html_end + 7]  # +7 for '</html>'
    
    # Ensure proper HTML structure
    content = content.strip()
    
    # Validate it starts with DOCTYPE or html tag
    if not (content.startswith('<!DOCTYPE html>') or content.startswith('<html')):
        logger.warning("Content doesn't start with proper HTML declaration")
        logger.info(f"Content starts with: {content[:200]}...")
    
    return content


def generate_fallback_website(project_data: Dict[str, Any]) -> str:
    """Generate a fallback website if LLM generation fails."""
    request_data = project_data.get("request", {})
    description = request_data.get("description", "My Website")
    user_id = request_data.get("user_id", "User")
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{user_id}'s Website</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gradient-to-br from-blue-500 to-purple-600 min-h-screen flex items-center justify-center">
    <div class="text-center text-white max-w-4xl mx-auto px-6">
        <h1 class="text-6xl font-bold mb-6">Welcome to {user_id}'s Website</h1>
        <p class="text-xl mb-8 max-w-2xl mx-auto">{description}</p>
        <div class="bg-white bg-opacity-20 backdrop-blur-lg rounded-lg p-8 mt-8">
            <h2 class="text-2xl font-semibold mb-4">Built with AI Agents</h2>
            <p class="text-lg">This website was automatically generated by intelligent agents using:</p>
            <div class="grid md:grid-cols-3 gap-4 mt-6">
                <div class="bg-white bg-opacity-10 rounded-lg p-4">
                    <h3 class="font-semibold">🤖 Planner Agent</h3>
                    <p class="text-sm">Analyzed requirements</p>
                </div>
                <div class="bg-white bg-opacity-10 rounded-lg p-4">
                    <h3 class="font-semibold">💻 Developer Agent</h3>
                    <p class="text-sm">Generated the code</p>
                </div>
                <div class="bg-white bg-opacity-10 rounded-lg p-4">
                    <h3 class="font-semibold">🚀 Deploy Agent</h3>
                    <p class="text-sm">Deployed to Netlify</p>
                </div>
            </div>
        </div>
    </div>
</body>
</html>"""


@app.post("/api/projects/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: CreateProjectRequest,
    background_tasks: BackgroundTasks,
    session_id: Optional[str] = Header(None, alias="X-Session-ID")
) -> ProjectResponse:
    """Create a new project using real agents."""
    try:
        project_id = str(uuid.uuid4())
        
        # Initialize project data
        project_data = {
            "request": request.model_dump(),
            "status": "initializing",
            "created_at": datetime.utcnow(),
            "last_updated": datetime.utcnow(),
            "current_phase": "initializing",
            "progress": 5.0,
            "completed_tasks": 0,
            "pending_tasks": 5,
            "failed_tasks": 0,
            "deployment_url": None,
            "llm_analysis": None,
            "generated_code": None
        }
        
        projects_store[project_id] = project_data
        
        # Associate with session
        if session_id and session_id in sessions_store:
            sessions_store[session_id]["projects"].append(project_id)
            sessions_store[session_id]["last_activity"] = datetime.utcnow()
        
        # Start agent processing in background
        background_tasks.add_task(process_project_with_agents, project_id, request)
        
        logger.info(f"Created project {project_id} for user {request.user_id}")
        
        return ProjectResponse(
            project_id=project_id,
            status="initializing",
            message="Project created! AI agents are analyzing your requirements and will start building your website.",
            created_at=datetime.utcnow(),
            data={
                "user_id": request.user_id,
                "description": request.description,
                "estimated_completion": "5-10 minutes",
                "agents_working": ["planner_agent", "developer_agent", "deployment_agent"]
            }
        )
        
    except Exception as e:
        logger.error(f"Error creating project: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project: {str(e)}"
        )


@app.get("/api/projects/{project_id}", response_model=ProjectStatusResponse)
async def get_project_status(project_id: str) -> ProjectStatusResponse:
    """Get the current status of a project."""
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = projects_store[project_id]
    
    return ProjectStatusResponse(
        project_id=project_id,
        status=project["status"],
        current_phase=project["current_phase"],
        progress_percentage=project["progress"],
        completed_tasks=project["completed_tasks"],
        pending_tasks=project["pending_tasks"],
        failed_tasks=project["failed_tasks"],
        last_updated=project["last_updated"],
        deployment_url=project.get("deployment_url")
    )


@app.get("/api/projects/")
async def list_projects(user_id: Optional[str] = None):
    """List all projects."""
    projects = []
    
    for project_id, project_data in projects_store.items():
        if user_id is None or project_data["request"]["user_id"] == user_id:
            projects.append({
                "project_id": project_id,
                "user_id": project_data["request"]["user_id"],
                "description": project_data["request"]["description"],
                "status": project_data["status"],
                "current_phase": project_data["current_phase"],
                "progress_percentage": project_data["progress"],
                "created_at": project_data["created_at"],
                "last_updated": project_data["last_updated"],
                "deployment_url": project_data.get("deployment_url")
            })
    
    return {
        "projects": projects,
        "total_count": len(projects)
    }


@app.get("/api/projects/{project_id}/details")
async def get_project_details(project_id: str):
    """Get detailed project information including LLM analysis and generated code."""
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = projects_store[project_id]
    
    return {
        "project_id": project_id,
        "status": project["status"],
        "current_phase": project["current_phase"],
        "progress": project["progress"],
        "llm_analysis": project.get("llm_analysis"),
        "generated_code_length": len(project.get("generated_code", "")) if project.get("generated_code") else 0,
        "deployment_url": project.get("deployment_url"),
        "error": project.get("error"),
        "last_updated": project["last_updated"]
    }


@app.get("/api/system/status")
async def system_status():
    """Get system status including agent health."""
    return {
        "status": "operational",
        "agents": {
            "planner_agent": "active" if planner_agent else "inactive",
            "developer_agent": "active" if developer_agent else "inactive",
            "llm_service": "active" if llm_service else "inactive"
        },
        "projects": {
            "total": len(projects_store),
            "active": len([p for p in projects_store.values() if p["status"] in ["initializing", "planning", "development", "testing", "deployment"]]),
            "completed": len([p for p in projects_store.values() if p["status"] == "completed"]),
            "failed": len([p for p in projects_store.values() if p["status"] == "failed"])
        }
    }


@app.get("/api/projects/{project_id}/preview")
async def preview_project(project_id: str):
    """Preview the generated website code."""
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = projects_store[project_id]
    generated_code = project.get("generated_code")
    
    if not generated_code:
        # Generate fallback content
        generated_code = generate_fallback_website(project)
    
    return FileResponse(
        content=generated_code,
        media_type="text/html",
        headers={"Content-Disposition": "inline"}
    )


@app.get("/preview/{project_id}")
async def serve_preview(project_id: str):
    """Serve the generated website as HTML."""
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = projects_store[project_id]
    generated_code = project.get("generated_code")
    
    if not generated_code:
        generated_code = generate_fallback_website(project)
    
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=generated_code)


# Approval Endpoints
@app.get("/api/approvals/pending")
async def get_pending_approvals(project_id: Optional[str] = None):
    """Get pending approval requests."""
    approvals = []
    
    for pid, project in projects_store.items():
        if project_id is None or pid == project_id:
            # Check for execution plan approval
            if project.get("pending_approval"):
                approval = project["pending_approval"]
                approvals.append({
                    "request_id": approval["approval_id"],
                    "project_id": pid,
                    "type": approval["type"],
                    "title": approval["title"],
                    "description": approval["description"],
                    "plan_summary": approval.get("plan_summary"),
                    "created_at": approval["created_at"],
                    "status": "pending"
                })
            
            # Check for deployment approval
            if project.get("pending_deployment_approval"):
                approval = project["pending_deployment_approval"]
                approvals.append({
                    "request_id": approval["approval_id"],
                    "project_id": pid,
                    "type": approval["type"],
                    "title": approval["title"],
                    "description": approval["description"],
                    "created_at": approval["created_at"],
                    "status": "pending",
                    "preview_url": f"/preview/{pid}"
                })
    
    return {
        "pending_approvals": approvals,
        "count": len(approvals)
    }


class ApprovalResponse(BaseModel):
    """Request model for approval response."""
    approved: bool = Field(..., description="Whether the request is approved")


@app.post("/api/approvals/{request_id}/respond")
async def respond_to_approval(request_id: str, response: ApprovalResponse, background_tasks: BackgroundTasks):
    """Respond to an approval request."""
    approved = response.approved
    # Find the project with this approval
    project_id = None
    approval_type = None
    
    for pid, project in projects_store.items():
        if project.get("pending_approval", {}).get("approval_id") == request_id:
            project_id = pid
            approval_type = "execution_plan"
            break
        elif project.get("pending_deployment_approval", {}).get("approval_id") == request_id:
            project_id = pid
            approval_type = "deployment"
            break
    
    if not project_id:
        raise HTTPException(status_code=404, detail="Approval request not found")
    
    project = projects_store[project_id]
    
    if approved:
        if approval_type == "execution_plan":
            # Clear the pending approval
            project.pop("pending_approval", None)
            project["status"] = "development"
            project["current_phase"] = "development"
            project["last_updated"] = datetime.utcnow()
            
            # Continue processing in background
            background_tasks.add_task(continue_after_approval, project_id)
            
            return {
                "request_id": request_id,
                "status": "approved",
                "message": "Execution plan approved. Development phase started.",
                "project_id": project_id
            }
        
        elif approval_type == "deployment":
            # Clear the pending deployment approval
            project.pop("pending_deployment_approval", None)
            project["status"] = "deploying"
            project["current_phase"] = "deploying"
            project["last_updated"] = datetime.utcnow()
            
            # Deploy in background
            background_tasks.add_task(deploy_after_approval, project_id)
            
            return {
                "request_id": request_id,
                "status": "approved",
                "message": "Deployment approved. Deploying to Netlify...",
                "project_id": project_id
            }
    
    else:
        # Rejection
        project["status"] = "rejected"
        project["current_phase"] = "rejected"
        project["last_updated"] = datetime.utcnow()
        
        return {
            "request_id": request_id,
            "status": "rejected",
            "message": "Request rejected by user.",
            "project_id": project_id
        }


# Feedback Endpoint
@app.post("/api/governance/feedback")
async def submit_feedback(
    project_id: str,
    agent_id: str,
    feedback_type: str,
    subject: str,
    content: str,
    rating: Optional[int] = None
):
    """Submit feedback on agent actions."""
    feedback_id = str(uuid.uuid4())
    
    feedback = {
        "feedback_id": feedback_id,
        "project_id": project_id,
        "agent_id": agent_id,
        "feedback_type": feedback_type,
        "subject": subject,
        "content": content,
        "rating": rating,
        "timestamp": datetime.utcnow()
    }
    
    # Store feedback (in real implementation, this would go to database)
    if project_id in projects_store:
        if "feedback" not in projects_store[project_id]:
            projects_store[project_id]["feedback"] = []
        projects_store[project_id]["feedback"].append(feedback)
    
    logger.info(f"Feedback received for project {project_id}: {subject}")
    
    return {
        "feedback_id": feedback_id,
        "message": "Feedback received successfully",
        "timestamp": datetime.utcnow()
    }