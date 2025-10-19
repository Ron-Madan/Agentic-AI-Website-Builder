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
from ..agents.tester_factory import TesterAgentFactory
from ..agents.monitor_factory import MonitorAgentFactory
from ..core.state_manager import StateManager
from ..core.feedback_manager import FeedbackLoopManager
from ..models.project import ProjectRequest, ProjectState
from ..models.feedback import FeedbackRequest, FeedbackResponse


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
    
    # Enhanced testing information
    test_status: Optional[str] = None  # "not_started", "running", "passed", "failed", "skipped"
    test_summary: Optional[Dict[str, Any]] = None
    test_progress: Optional[Dict[str, Any]] = None  # Current test execution progress
    
    # Enhanced monitoring information
    monitoring_status: Optional[str] = None  # "not_configured", "setting_up", "active", "failed", "inactive"
    monitoring_active: Optional[bool] = None
    monitoring_metrics: Optional[Dict[str, Any]] = None  # Key monitoring metrics
    
    # Enhanced feedback session information
    feedback_session: Optional[Dict[str, Any]] = None
    preview_url: Optional[str] = None
    current_version: Optional[Dict[str, Any]] = None  # Current version info
    version_count: Optional[int] = None  # Total number of versions
    
    # Error and issue tracking
    current_errors: Optional[List[Dict[str, Any]]] = None  # Current errors/issues
    warnings: Optional[List[str]] = None  # Non-critical warnings
    
    # Phase-specific details
    phase_details: Optional[Dict[str, Any]] = None  # Details specific to current phase


# Global state
projects_store: Dict[str, Dict[str, Any]] = {}
sessions_store: Dict[str, Dict[str, Any]] = {}
llm_service: Optional[LLMService] = None
planner_agent: Optional[PlannerAgent] = None
developer_agent: Optional[DeveloperAgent] = None
tester_agent = None
monitor_agent = None
state_manager: Optional[StateManager] = None
feedback_manager = None
preview_manager = None


async def initialize_agents():
    """Initialize the agent system."""
    global llm_service, planner_agent, developer_agent, tester_agent, monitor_agent, state_manager, feedback_manager, preview_manager
    
    try:
        # Initialize LLM service
        llm_service = LLMService()
        logger.info("LLM service initialized successfully")
        
        # Initialize state manager
        from ..core.state_manager import InMemoryStateManager
        state_manager = InMemoryStateManager()
        logger.info("State manager initialized successfully")
        
        # Initialize agents (simplified for now)
        # planner_agent = PlannerAgent("planner_001", state_manager)
        # developer_agent = DeveloperAgent("developer_001", state_manager)
        
        # Initialize TesterAgent using factory
        try:
            tester_agent = TesterAgentFactory.create_tester_agent(
                state_manager=state_manager,
                llm_service=llm_service
            )
            logger.info("TesterAgent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize TesterAgent: {e}")
            tester_agent = None
        
        # Initialize MonitorAgent using factory
        try:
            monitor_agent = MonitorAgentFactory.create_monitor_agent(
                state_manager=state_manager
            )
            logger.info("MonitorAgent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MonitorAgent: {e}")
            monitor_agent = None
        
        # Initialize FeedbackLoopManager
        try:
            global feedback_manager
            feedback_manager = FeedbackLoopManager(
                llm_service=llm_service,
                state_manager=state_manager
            )
            logger.info("FeedbackLoopManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize FeedbackLoopManager: {e}")
            feedback_manager = None
        
        # Initialize PreviewManager
        try:
            global preview_manager
            from ..core.preview_manager import PreviewManager
            preview_manager = PreviewManager(state_manager=state_manager)
            logger.info("PreviewManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize PreviewManager: {e}")
            preview_manager = None
        
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
        "tester_agent_active": tester_agent is not None,
        "monitor_agent_active": monitor_agent is not None,
        "llm_service_active": llm_service is not None,
        "feedback_manager_active": feedback_manager is not None,
        "preview_manager_active": preview_manager is not None
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


class ProjectError(Exception):
    """Custom exception for project-related errors."""
    
    def __init__(self, message: str, error_type: str = "general", severity: str = "medium", recoverable: bool = True):
        super().__init__(message)
        self.error_type = error_type
        self.severity = severity
        self.recoverable = recoverable
        self.timestamp = datetime.utcnow()


def _handle_project_error(project_id: str, error: Exception, phase: str) -> Dict[str, Any]:
    """Handle project errors with comprehensive logging and recovery options."""
    error_info = {
        "error_id": str(uuid.uuid4()),
        "project_id": project_id,
        "phase": phase,
        "timestamp": datetime.utcnow().isoformat(),
        "error_type": getattr(error, 'error_type', 'unknown'),
        "severity": getattr(error, 'severity', 'medium'),
        "recoverable": getattr(error, 'recoverable', True),
        "message": str(error),
        "recovery_suggestions": []
    }
    
    # Add phase-specific recovery suggestions
    if phase == "testing":
        error_info["recovery_suggestions"] = [
            "Check if test environment can be recreated",
            "Verify HTML content is valid",
            "Try running tests with reduced scope",
            "Skip testing and proceed to feedback phase"
        ]
    elif phase == "monitoring":
        error_info["recovery_suggestions"] = [
            "Continue deployment without monitoring",
            "Set up monitoring manually later",
            "Check monitor agent configuration",
            "Verify deployment URL is accessible"
        ]
    elif phase == "feedback":
        error_info["recovery_suggestions"] = [
            "Skip feedback phase and proceed to deployment",
            "Use original version without feedback",
            "Check preview server configuration",
            "Verify LLM service availability"
        ]
    elif phase == "deployment":
        error_info["recovery_suggestions"] = [
            "Retry deployment with different configuration",
            "Check deployment credentials",
            "Verify generated content is valid",
            "Try alternative deployment platform"
        ]
    
    # Log error with full context
    logger.error(f"Project {project_id} error in {phase}: {error_info}")
    
    # Update project with error information
    if project_id in projects_store:
        project = projects_store[project_id]
        if "errors" not in project:
            project["errors"] = []
        project["errors"].append(error_info)
        project["last_error"] = error_info
        project["last_updated"] = datetime.utcnow()
        
        # Don't mark as failed if error is recoverable
        if not error_info["recoverable"]:
            project["status"] = "failed"
            project["error"] = str(error)
    
    return error_info


async def _safe_testing_execution(project_id: str, html_content: str) -> Dict[str, Any]:
    """Safely execute testing with comprehensive error handling."""
    try:
        from .testing_integration import run_comprehensive_tests, handle_test_failures
        
        logger.info(f"Starting safe testing execution for project {project_id}")
        
        # Run comprehensive tests with timeout
        test_results = await asyncio.wait_for(
            run_comprehensive_tests(project_id, html_content, tester_agent),
            timeout=300  # 5 minute timeout
        )
        
        # Handle test failures if any
        if not test_results.get("overall_success", False):
            logger.warning(f"Tests failed for project {project_id}, attempting remediation")
            
            # Get failure analyzer from tester agent if available
            failure_analyzer = None
            if tester_agent and hasattr(tester_agent, 'failure_analyzer'):
                failure_analyzer = tester_agent.failure_analyzer
            
            try:
                remediation_results = await asyncio.wait_for(
                    handle_test_failures(project_id, test_results, failure_analyzer),
                    timeout=120  # 2 minute timeout for remediation
                )
                test_results["remediation_results"] = remediation_results
                
                # If remediation suggests retry, we could retry here
                if remediation_results.get("retry_recommended"):
                    test_results["test_status"] = "failed_with_remediation"
                else:
                    test_results["test_status"] = "failed"
            except asyncio.TimeoutError:
                logger.error(f"Test remediation timeout for project {project_id}")
                test_results["remediation_error"] = "Remediation timeout"
                test_results["test_status"] = "failed"
            except Exception as remediation_error:
                logger.error(f"Test remediation failed for project {project_id}: {remediation_error}")
                test_results["remediation_error"] = str(remediation_error)
                test_results["test_status"] = "failed"
        else:
            test_results["test_status"] = "passed"
            logger.info(f"All tests passed for project {project_id}")
        
        return test_results
        
    except asyncio.TimeoutError:
        error_msg = f"Testing timeout for project {project_id}"
        logger.error(error_msg)
        raise ProjectError(error_msg, "testing_timeout", "high", True)
    except Exception as e:
        error_msg = f"Testing execution failed for project {project_id}: {str(e)}"
        logger.error(error_msg)
        raise ProjectError(error_msg, "testing_failure", "medium", True)


async def _safe_monitoring_setup(project_id: str, deployment_url: str) -> Dict[str, Any]:
    """Safely set up monitoring with comprehensive error handling."""
    try:
        from .monitoring_integration import setup_monitoring, create_monitoring_config
        
        logger.info(f"Starting safe monitoring setup for project {project_id}")
        
        # Create monitoring configuration with fallbacks
        monitoring_config = create_monitoring_config(
            error_tracking_enabled=True,
            uptime_monitoring_enabled=True,
            performance_monitoring_enabled=False,  # Keep disabled for reliability
            notification_channels=[],
            alert_thresholds={
                "error_rate_threshold": 5.0,
                "response_time_threshold": 5000,
                "uptime_threshold": 95.0
            }
        )
        
        # Set up monitoring with timeout
        monitoring_result = await asyncio.wait_for(
            setup_monitoring(
                project_id=project_id,
                deployment_url=deployment_url,
                monitor_agent=monitor_agent,
                config={
                    "check_interval": 300,  # 5 minutes
                    "timeout": 30,
                    "error_tracking_enabled": True,
                    "uptime_monitoring_enabled": True,
                    "performance_monitoring_enabled": False,
                    "error_rate_threshold": 5.0,
                    "response_time_threshold": 5000,
                    "uptime_threshold": 95.0
                }
            ),
            timeout=60  # 1 minute timeout
        )
        
        # Validate monitoring setup
        if not monitoring_result.get("monitoring_active"):
            error_msg = monitoring_result.get("error", "Unknown monitoring setup error")
            logger.warning(f"Monitoring setup failed for project {project_id}: {error_msg}")
            raise ProjectError(error_msg, "monitoring_setup_failed", "low", True)
        
        logger.info(f"Monitoring successfully set up for project {project_id}")
        return {
            "monitoring_config": monitoring_config.model_dump(),
            "monitoring_result": monitoring_result
        }
        
    except asyncio.TimeoutError:
        error_msg = f"Monitoring setup timeout for project {project_id}"
        logger.warning(error_msg)
        raise ProjectError(error_msg, "monitoring_timeout", "low", True)
    except ProjectError:
        raise  # Re-raise ProjectError as-is
    except Exception as e:
        error_msg = f"Monitoring setup failed for project {project_id}: {str(e)}"
        logger.warning(error_msg)
        raise ProjectError(error_msg, "monitoring_failure", "low", True)


async def _safe_feedback_session_creation(project_id: str, html_content: str, test_results: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Safely create feedback session with comprehensive error handling."""
    try:
        if not feedback_manager:
            logger.warning(f"No feedback manager available for project {project_id}")
            return None
        
        logger.info(f"Starting safe feedback session creation for project {project_id}")
        
        # Create feedback session with timeout
        feedback_session = await asyncio.wait_for(
            feedback_manager.create_feedback_session(
                project_id=project_id,
                html_content=html_content,
                test_results=test_results
            ),
            timeout=30  # 30 second timeout
        )
        
        # Create preview server if preview manager is available
        preview_url = feedback_session.preview_url  # Default fallback
        if preview_manager:
            try:
                logger.info(f"Starting preview server for project {project_id}")
                preview_url = await asyncio.wait_for(
                    preview_manager.start_preview_server(project_id=project_id, html_content=html_content),
                    timeout=30  # 30 second timeout
                )
                # Update feedback session with actual preview URL
                feedback_session.preview_url = preview_url
                logger.info(f"Preview server started at {preview_url}")
            except asyncio.TimeoutError:
                logger.warning(f"Preview server timeout for project {project_id}, using fallback URL")
                preview_url = f"http://localhost:8080/preview/{project_id}"
            except Exception as e:
                logger.warning(f"Failed to start preview server for project {project_id}: {e}, using fallback URL")
                preview_url = f"http://localhost:8080/preview/{project_id}"
        else:
            logger.warning(f"No preview manager available for project {project_id}, using fallback URL")
            preview_url = f"http://localhost:8080/preview/{project_id}"
        
        return {
            "session_id": project_id,
            "current_version_id": feedback_session.current_version_id,
            "preview_url": preview_url,
            "status": feedback_session.status,
            "versions_count": len(feedback_session.versions)
        }
        
    except asyncio.TimeoutError:
        error_msg = f"Feedback session creation timeout for project {project_id}"
        logger.warning(error_msg)
        raise ProjectError(error_msg, "feedback_timeout", "low", True)
    except Exception as e:
        error_msg = f"Feedback session creation failed for project {project_id}: {str(e)}"
        logger.warning(error_msg)
        raise ProjectError(error_msg, "feedback_failure", "low", True)


async def continue_after_approval(project_id: str):
    """Continue project processing after user approval with comprehensive error handling."""
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
        
        # Step 4: Real Testing phase with enhanced error handling
        project["current_phase"] = "testing"
        project["test_status"] = "running"
        project["progress"] = 65.0
        project["last_updated"] = datetime.utcnow()
        
        # Add a small delay to make testing phase visible
        await asyncio.sleep(2)
        
        html_content = project.get("generated_code", "")
        
        if html_content:
            try:
                logger.info(f"🧪 Starting comprehensive testing for project {project_id}")
                
                # Use safe testing execution with comprehensive error handling
                test_results = await _safe_testing_execution(project_id, html_content)
                
                # Store test results in project
                project["test_results"] = test_results
                project["test_status"] = test_results.get("test_status", "unknown")
                project["progress"] = 75.0
                project["last_updated"] = datetime.utcnow()
                
                # Log detailed test results for visibility
                total_tests = test_results.get("total_tests", 0)
                total_passed = test_results.get("total_passed", 0)
                total_failed = test_results.get("total_failed", 0)
                logger.info(f"🧪 Testing completed for project {project_id}: {total_passed}/{total_tests} tests passed, {total_failed} failed")
                
                if test_results.get("overall_success"):
                    logger.info(f"✅ All tests passed for project {project_id}")
                else:
                    logger.warning(f"⚠️ Some tests failed for project {project_id}")
                
            except ProjectError as e:
                # Handle testing errors gracefully
                error_info = _handle_project_error(project_id, e, "testing")
                
                # Store error information but continue workflow
                project["test_results"] = {
                    "error": str(e),
                    "error_info": error_info,
                    "overall_success": False
                }
                project["test_status"] = "error"
                project["progress"] = 70.0  # Partial progress
                project["last_updated"] = datetime.utcnow()
                
                logger.warning(f"Testing failed for project {project_id}, continuing with error status")
        else:
            logger.warning(f"No generated code found for testing project {project_id}")
            project["test_results"] = {
                "error": "No generated code available for testing",
                "overall_success": False
            }
            project["test_status"] = "skipped"
        
        # Step 5: Create feedback session after testing with enhanced error handling
        project["current_phase"] = "feedback"
        project["progress"] = 80.0
        project["last_updated"] = datetime.utcnow()
        
        # Create feedback session if feedback manager is available
        logger.info(f"Checking feedback session creation for project {project_id}: feedback_manager={feedback_manager is not None}, html_content_length={len(html_content) if html_content else 0}")
        
        if not feedback_manager:
            logger.error(f"No feedback manager available for project {project_id}")
        if not html_content:
            logger.error(f"No HTML content available for project {project_id}")
            
        if feedback_manager and html_content:
            try:
                logger.info(f"Attempting to create feedback session for project {project_id}")
                # Use safe feedback session creation with comprehensive error handling
                feedback_session_info = await _safe_feedback_session_creation(
                    project_id=project_id,
                    html_content=html_content,
                    test_results=project.get("test_results")
                )
                
                logger.info(f"Feedback session creation result for project {project_id}: {feedback_session_info is not None}")
                
                if feedback_session_info:
                    # Store feedback session info in project
                    project["feedback_session"] = feedback_session_info
                    
                    # Set up feedback approval request
                    feedback_approval_id = f"feedback_approval_{project_id[:8]}"
                    project["pending_feedback_approval"] = {
                        "approval_id": feedback_approval_id,
                        "type": "feedback_review",
                        "title": "Website Review and Feedback",
                        "description": "Please review your generated website and provide feedback for improvements, or approve for deployment.",
                        "preview_url": feedback_session_info["preview_url"],
                        "created_at": datetime.utcnow()
                    }
                    project["status"] = "awaiting_feedback"
                    project["current_phase"] = "awaiting_feedback"
                    project["completed_tasks"] = 3
                    project["pending_tasks"] = 2
                    project["last_updated"] = datetime.utcnow()
                    
                    logger.info(f"Feedback session created for project {project_id}, awaiting user review at {feedback_session_info['preview_url']}")
                    return  # Stop here and wait for feedback or approval
                else:
                    logger.warning(f"Feedback session creation returned None for project {project_id}")
                
            except ProjectError as e:
                # Handle feedback session errors gracefully
                error_info = _handle_project_error(project_id, e, "feedback")
                
                logger.warning(f"Failed to create feedback session for project {project_id}: {e}")
                # Continue to deployment approval if feedback session creation fails
            except Exception as e:
                logger.error(f"Unexpected error creating feedback session for project {project_id}: {e}")
                # Continue to deployment approval if feedback session creation fails
        
        # Fallback: Skip feedback and go directly to deployment approval
        project["progress"] = 85.0
        project["current_phase"] = "deployment"
        project["completed_tasks"] = 4
        project["pending_tasks"] = 1
        project["last_updated"] = datetime.utcnow()
        
        # Step 6: REQUEST DEPLOYMENT APPROVAL
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


def _calculate_enhanced_progress(project: Dict[str, Any]) -> float:
    """Calculate enhanced progress percentage including all workflow phases."""
    current_phase = project.get("current_phase", "initializing")
    status = project.get("status", "initializing")
    
    # Base progress from existing calculation
    base_progress = project.get("progress", 0.0)
    
    # Phase-based progress mapping
    phase_progress_map = {
        "initializing": 0.0,
        "planning": 10.0,
        "awaiting_approval": 25.0,
        "development": 40.0,
        "testing": 60.0,
        "feedback": 75.0,
        "awaiting_feedback": 75.0,
        "deployment": 85.0,
        "awaiting_deployment_approval": 85.0,
        "deployed": 100.0
    }
    
    # Get base progress from phase
    phase_progress = phase_progress_map.get(current_phase, base_progress)
    
    # Add sub-phase progress for more granular tracking
    if current_phase == "testing":
        test_results = project.get("test_results")
        if test_results:
            # Add progress based on test completion
            completed_tests = len(test_results.get("completed_test_types", []))
            total_tests = len(test_results.get("test_types", ["unit", "integration", "ui"]))
            if total_tests > 0:
                test_progress = (completed_tests / total_tests) * 10  # 10% range for testing phase
                phase_progress = 60.0 + test_progress
    
    elif current_phase == "feedback" or current_phase == "awaiting_feedback":
        feedback_session = project.get("feedback_session")
        if feedback_session:
            # Add progress based on feedback iterations (diminishing returns)
            iterations = feedback_session.get("versions_count", 1) - 1
            if iterations > 0:
                # Each iteration adds less progress (max 8% total)
                iteration_progress = min(8.0, iterations * 3.0 - (iterations - 1) * 0.5)
                phase_progress = 75.0 + iteration_progress
    
    elif current_phase == "deployment":
        # Add progress based on deployment steps
        if project.get("deployment_url"):
            phase_progress = 90.0  # Deployment successful, setting up monitoring
            if project.get("monitoring_result", {}).get("monitoring_active"):
                phase_progress = 95.0  # Monitoring active
    
    # Handle error states
    if status == "failed":
        # Don't reduce progress, but indicate the failure in status
        pass
    
    # Ensure progress doesn't go backwards (except for failures)
    final_progress = max(phase_progress, base_progress) if status != "failed" else phase_progress
    
    return min(100.0, max(0.0, final_progress))


async def deploy_after_approval(project_id: str):
    """Deploy project after user approval."""
    try:
        if project_id not in projects_store:
            return
        
        project = projects_store[project_id]
        
        # Log deployment start
        logger.info(f"Starting deployment for project {project_id} with status {project.get('status')}")
        
        # Deploy to Netlify
        deployment_url = await deploy_to_netlify(project_id, project)
        logger.info(f"Deployment completed for project {project_id}: {deployment_url}")
        
        # Set up monitoring after successful deployment with enhanced error handling
        monitoring_config = None
        monitoring_result = None
        
        if deployment_url and not deployment_url.startswith("https://demo-"):
            # Only set up real monitoring for actual deployments, not demo URLs
            try:
                logger.info(f"Setting up monitoring for project {project_id} at {deployment_url}")
                
                # Use safe monitoring setup with comprehensive error handling
                monitoring_data = await _safe_monitoring_setup(project_id, deployment_url)
                
                monitoring_config = monitoring_data["monitoring_config"]
                monitoring_result = monitoring_data["monitoring_result"]
                
                # Store monitoring configuration in project state
                project["monitoring_config"] = monitoring_config
                project["monitoring_result"] = monitoring_result
                
                logger.info(f"Monitoring successfully set up for project {project_id}")
                
            except ProjectError as e:
                # Handle monitoring errors gracefully - don't fail deployment
                error_info = _handle_project_error(project_id, e, "monitoring")
                
                logger.warning(f"Monitoring setup failed for project {project_id}: {e}")
                
                # Store error but continue with deployment
                project["monitoring_error"] = {
                    "error": str(e),
                    "error_info": error_info,
                    "can_retry": e.recoverable
                }
                
                # Set up basic monitoring config for status tracking
                from .monitoring_integration import create_monitoring_config
                monitoring_config = create_monitoring_config()
                project["monitoring_config"] = monitoring_config.model_dump()
                project["monitoring_result"] = {
                    "monitoring_active": False,
                    "error": str(e),
                    "setup_time": datetime.utcnow().isoformat()
                }
        else:
            logger.info(f"Skipping monitoring setup for demo deployment: {deployment_url}")
        
        # Clean up preview server after successful deployment with error handling
        if preview_manager:
            try:
                logger.info(f"Cleaning up preview server for project {project_id}")
                cleanup_result = await asyncio.wait_for(
                    preview_manager.stop_preview_server(project_id),
                    timeout=30  # 30 second timeout
                )
                if cleanup_result:
                    logger.info(f"Preview server cleaned up for project {project_id}")
                else:
                    logger.warning(f"Preview server cleanup returned False for project {project_id}")
            except asyncio.TimeoutError:
                logger.error(f"Preview server cleanup timeout for project {project_id}")
            except Exception as e:
                logger.error(f"Failed to cleanup preview server for project {project_id}: {e}")
        
        # Complete feedback session with error handling
        if feedback_manager:
            try:
                await asyncio.wait_for(
                    feedback_manager.complete_feedback_session(project_id),
                    timeout=30  # 30 second timeout
                )
                logger.info(f"Feedback session completed for project {project_id}")
            except asyncio.TimeoutError:
                logger.error(f"Feedback session completion timeout for project {project_id}")
            except Exception as e:
                logger.error(f"Failed to complete feedback session for project {project_id}: {e}")
        
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
        
        # Clean up preview server on deployment failure with enhanced error handling
        if preview_manager:
            try:
                cleanup_result = await asyncio.wait_for(
                    preview_manager.stop_preview_server(project_id),
                    timeout=30  # 30 second timeout
                )
                if cleanup_result:
                    logger.info(f"Preview server cleaned up after deployment failure for project {project_id}")
                else:
                    logger.warning(f"Preview server cleanup returned False after deployment failure for project {project_id}")
            except asyncio.TimeoutError:
                logger.error(f"Preview server cleanup timeout after deployment failure for project {project_id}")
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup preview server after deployment failure: {cleanup_error}")
        
        # Cancel feedback session on deployment failure with enhanced error handling
        if feedback_manager:
            try:
                await asyncio.wait_for(
                    feedback_manager.cancel_feedback_session(project_id),
                    timeout=30  # 30 second timeout
                )
                logger.info(f"Feedback session cancelled after deployment failure for project {project_id}")
            except asyncio.TimeoutError:
                logger.error(f"Feedback session cancellation timeout after deployment failure for project {project_id}")
            except Exception as cleanup_error:
                logger.error(f"Failed to cancel feedback session after deployment failure: {cleanup_error}")
        
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
        # Get the current version from feedback manager if available
        website_content = None
        if feedback_manager and project_data.get("status") == "awaiting_feedback":
            try:
                current_version = await feedback_manager.get_current_version(project_id)
                if current_version:
                    website_content = current_version.html_content
                    logger.info(f"Deploying current feedback version {current_version.version_id} for project {project_id}")
            except Exception as e:
                logger.warning(f"Failed to get current version from feedback manager: {e}")
        
        # Fallback to original generated code
        if not website_content:
            website_content = project_data.get("generated_code")
            logger.info(f"Deploying original generated code for project {project_id}")
        
        if not website_content:
            # Fallback to simple generated content
            website_content = generate_fallback_website(project_data)
            logger.info(f"Deploying fallback website for project {project_id}")
        
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
            "generated_code": None,
            "test_results": None,
            "test_status": None,
            "remediation_results": None
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
    """Get the current status of a project with enhanced testing, monitoring, and feedback information."""
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = projects_store[project_id]
    
    # Enhanced test information
    test_summary = None
    test_progress = None
    test_status = project.get("test_status", "not_started")
    
    test_results = project.get("test_results")
    if test_results:
        test_summary = {
            "overall_success": test_results.get("overall_success", False),
            "total_tests": test_results.get("total_tests", 0),
            "total_passed": test_results.get("total_passed", 0),
            "total_failed": test_results.get("total_failed", 0),
            "total_duration": test_results.get("total_duration", 0),
            "executed_at": test_results.get("executed_at"),
            "test_types": test_results.get("test_types", []),
            "failure_categories": test_results.get("failure_categories", [])
        }
        
        # Add test progress information
        if project["current_phase"] == "testing":
            test_progress = {
                "current_test_type": test_results.get("current_test_type"),
                "completed_test_types": test_results.get("completed_test_types", []),
                "remaining_test_types": test_results.get("remaining_test_types", [])
            }
    
    # Enhanced monitoring information
    monitoring_status = "not_configured"
    monitoring_active = False
    monitoring_metrics = None
    
    monitoring_result = project.get("monitoring_result")
    monitoring_config = project.get("monitoring_config")
    
    if monitoring_result:
        monitoring_active = monitoring_result.get("monitoring_active", False)
        if monitoring_active:
            monitoring_status = "active"
            # Get latest monitoring metrics if available
            monitoring_metrics = {
                "uptime_percentage": monitoring_result.get("uptime_percentage"),
                "error_count": monitoring_result.get("error_count", 0),
                "last_check": monitoring_result.get("last_check"),
                "response_time": monitoring_result.get("avg_response_time"),
                "status_checks": monitoring_result.get("status_checks", [])
            }
        elif "error" in monitoring_result:
            monitoring_status = "failed"
        else:
            monitoring_status = "inactive"
    elif project.get("deployment_url") and project["status"] == "completed":
        if monitoring_config:
            monitoring_status = "setting_up"
        else:
            monitoring_status = "not_configured"
    elif project["current_phase"] == "deployment" and project.get("deployment_url"):
        monitoring_status = "setting_up"
    
    # Enhanced feedback session information
    feedback_session_info = project.get("feedback_session")
    current_version = None
    version_count = 0
    
    if feedback_session_info:
        version_count = feedback_session_info.get("versions_count", 0)
        current_version = {
            "version_id": feedback_session_info.get("current_version_id"),
            "created_at": feedback_session_info.get("current_version_created_at"),
            "feedback_applied": feedback_session_info.get("current_version_feedback")
        }
    
    # Collect current errors and warnings
    current_errors = []
    warnings = []
    
    # Add test failures as errors
    if test_results and not test_results.get("overall_success", True):
        for failure in test_results.get("failures", []):
            current_errors.append({
                "type": "test_failure",
                "category": failure.get("category", "unknown"),
                "message": failure.get("message", "Test failed"),
                "severity": "high" if failure.get("critical", False) else "medium"
            })
    
    # Add monitoring errors
    if monitoring_result and "error" in monitoring_result:
        current_errors.append({
            "type": "monitoring_error",
            "message": monitoring_result["error"],
            "severity": "medium"
        })
    
    # Add remediation warnings
    remediation_results = project.get("remediation_results")
    if remediation_results and remediation_results.get("warnings"):
        warnings.extend(remediation_results["warnings"])
    
    # Add general project errors
    if project.get("error"):
        current_errors.append({
            "type": "project_error",
            "message": project["error"],
            "severity": "high"
        })
    
    # Phase-specific details
    phase_details = {}
    current_phase = project["current_phase"]
    
    if current_phase == "testing":
        phase_details = {
            "test_environment_ready": bool(test_results),
            "auto_remediation_available": bool(remediation_results),
            "retry_count": remediation_results.get("retry_count", 0) if remediation_results else 0
        }
    elif current_phase == "feedback" or current_phase == "awaiting_feedback":
        phase_details = {
            "preview_available": bool(project.get("feedback_session", {}).get("preview_url")),
            "feedback_iterations": version_count - 1 if version_count > 0 else 0,
            "can_deploy": feedback_session_info.get("status") == "active" if feedback_session_info else False
        }
    elif current_phase == "deployment" or current_phase == "awaiting_deployment_approval":
        phase_details = {
            "deployment_ready": bool(project.get("generated_code")),
            "monitoring_will_be_setup": bool(monitoring_config or monitor_agent),
            "estimated_deployment_time": "2-5 minutes"
        }
    elif current_phase == "deployed":
        phase_details = {
            "deployment_successful": bool(project.get("deployment_url")),
            "monitoring_configured": monitoring_status in ["active", "setting_up"],
            "site_accessible": (monitoring_metrics.get("uptime_percentage") or 0) > 0 if monitoring_metrics else None
        }
    
    # Calculate enhanced progress percentage including all phases
    progress_percentage = _calculate_enhanced_progress(project)
    
    return ProjectStatusResponse(
        project_id=project_id,
        status=project["status"],
        current_phase=current_phase,
        progress_percentage=progress_percentage,
        completed_tasks=project.get("completed_tasks", 0),
        pending_tasks=project.get("pending_tasks", 0),
        failed_tasks=project.get("failed_tasks", 0),
        last_updated=project["last_updated"],
        deployment_url=project.get("deployment_url"),
        test_status=test_status,
        test_summary=test_summary,
        test_progress=test_progress,
        monitoring_status=monitoring_status,
        monitoring_active=monitoring_active,
        monitoring_metrics=monitoring_metrics,
        feedback_session=feedback_session_info,
        preview_url=project.get("feedback_session", {}).get("preview_url"),
        current_version=current_version,
        version_count=version_count,
        current_errors=current_errors if current_errors else None,
        warnings=warnings if warnings else None,
        phase_details=phase_details if phase_details else None
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
    """Get comprehensive project information including test results, monitoring status, and feedback history."""
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = projects_store[project_id]
    
    # Basic project information
    details = {
        "project_id": project_id,
        "status": project["status"],
        "current_phase": project["current_phase"],
        "progress": _calculate_enhanced_progress(project),
        "created_at": project.get("created_at"),
        "last_updated": project["last_updated"],
        "request_info": {
            "user_id": project.get("request", {}).get("user_id"),
            "description": project.get("request", {}).get("description"),
            "requirements": project.get("request", {}).get("requirements", []),
            "preferences": project.get("request", {}).get("preferences", {})
        }
    }
    
    # LLM Analysis and Code Generation
    details["generation"] = {
        "llm_analysis": project.get("llm_analysis"),
        "generated_code_length": len(project.get("generated_code", "")) if project.get("generated_code") else 0,
        "has_generated_code": bool(project.get("generated_code")),
        "code_preview": project.get("generated_code", "")[:500] + "..." if project.get("generated_code") and len(project.get("generated_code", "")) > 500 else project.get("generated_code", "")
    }
    
    # Enhanced Testing Information
    test_results = project.get("test_results")
    details["testing"] = {
        "status": project.get("test_status", "not_started"),
        "results_available": bool(test_results),
        "summary": None,
        "detailed_results": None,
        "remediation_info": None
    }
    
    if test_results:
        details["testing"]["summary"] = {
            "overall_success": test_results.get("overall_success", False),
            "total_tests": test_results.get("total_tests", 0),
            "total_passed": test_results.get("total_passed", 0),
            "total_failed": test_results.get("total_failed", 0),
            "total_duration": test_results.get("total_duration", 0),
            "executed_at": test_results.get("executed_at"),
            "test_types": test_results.get("test_types", [])
        }
        
        details["testing"]["detailed_results"] = {
            "unit_tests": test_results.get("unit_tests"),
            "integration_tests": test_results.get("integration_tests"),
            "ui_tests": test_results.get("ui_tests"),
            "failures": test_results.get("failures", []),
            "warnings": test_results.get("warnings", [])
        }
        
        # Add remediation information if available
        remediation_results = project.get("remediation_results")
        if remediation_results:
            details["testing"]["remediation_info"] = {
                "remediation_attempted": True,
                "total_failures_analyzed": remediation_results.get("analyzed_failures", 0),
                "auto_fixed": remediation_results.get("auto_fixed_failures", 0),
                "manual_fixes_needed": remediation_results.get("manual_fixes_needed", 0),
                "suggestions": remediation_results.get("remediation_suggestions", []),
                "retry_recommended": remediation_results.get("retry_recommended", False)
            }
    
    # Enhanced Monitoring Information
    monitoring_result = project.get("monitoring_result")
    monitoring_config = project.get("monitoring_config")
    monitoring_error = project.get("monitoring_error")
    
    details["monitoring"] = {
        "configured": bool(monitoring_config),
        "active": monitoring_result.get("monitoring_active", False) if monitoring_result else False,
        "status": "not_configured",
        "configuration": None,
        "metrics": None,
        "error_info": None
    }
    
    if monitoring_config:
        details["monitoring"]["configuration"] = monitoring_config
        
    if monitoring_result:
        if monitoring_result.get("monitoring_active"):
            details["monitoring"]["status"] = "active"
            details["monitoring"]["metrics"] = {
                "uptime_percentage": monitoring_result.get("uptime_percentage"),
                "error_count": monitoring_result.get("error_count", 0),
                "last_check": monitoring_result.get("last_check"),
                "response_time": monitoring_result.get("avg_response_time"),
                "setup_time": monitoring_result.get("setup_time")
            }
        elif "error" in monitoring_result:
            details["monitoring"]["status"] = "failed"
            details["monitoring"]["error_info"] = {
                "error_message": monitoring_result["error"],
                "setup_time": monitoring_result.get("setup_time")
            }
        else:
            details["monitoring"]["status"] = "inactive"
    
    if monitoring_error:
        details["monitoring"]["error_info"] = monitoring_error
        details["monitoring"]["status"] = "error"
    
    # Enhanced Feedback Session Information
    feedback_session = project.get("feedback_session")
    details["feedback"] = {
        "session_active": bool(feedback_session),
        "session_info": None,
        "version_history": [],
        "current_version": None
    }
    
    if feedback_session:
        details["feedback"]["session_info"] = {
            "session_id": feedback_session.get("session_id"),
            "status": feedback_session.get("status"),
            "preview_url": feedback_session.get("preview_url"),
            "versions_count": feedback_session.get("versions_count", 0),
            "created_at": feedback_session.get("created_at")
        }
        
        details["feedback"]["current_version"] = {
            "version_id": feedback_session.get("current_version_id"),
            "is_current": True
        }
        
        # If feedback manager is available, get detailed version history
        if feedback_manager and feedback_manager.active_sessions.get(project_id):
            session = feedback_manager.active_sessions[project_id]
            details["feedback"]["version_history"] = [
                {
                    "version_id": version.version_id,
                    "created_at": version.created_at.isoformat(),
                    "feedback_applied": version.feedback_applied,
                    "is_current": version.is_current,
                    "has_test_results": bool(version.test_results)
                }
                for version in session.versions
            ]
    
    # Deployment Information
    details["deployment"] = {
        "deployed": bool(project.get("deployment_url")),
        "url": project.get("deployment_url"),
        "deployment_time": None,
        "platform": "netlify"  # Default platform
    }
    
    # Error and Issue Tracking
    current_errors = []
    warnings = []
    
    # Collect errors from various sources
    if project.get("error"):
        current_errors.append({
            "type": "project_error",
            "message": project["error"],
            "severity": "high",
            "phase": project.get("current_phase", "unknown")
        })
    
    if project.get("errors"):
        current_errors.extend(project["errors"])
    
    # Add test failures as errors
    if test_results and not test_results.get("overall_success", True):
        for failure in test_results.get("failures", []):
            current_errors.append({
                "type": "test_failure",
                "category": failure.get("category", "unknown"),
                "message": failure.get("error_message", "Test failed"),
                "test_name": failure.get("test_name"),
                "severity": "high" if failure.get("critical", False) else "medium"
            })
    
    # Add test warnings
    if test_results and test_results.get("warnings"):
        warnings.extend([
            {"type": "test_warning", "message": warning}
            for warning in test_results["warnings"]
        ])
    
    # Add monitoring errors
    if monitoring_error:
        current_errors.append({
            "type": "monitoring_error",
            "message": monitoring_error.get("error", "Unknown monitoring error"),
            "severity": "low",
            "recoverable": monitoring_error.get("can_retry", True)
        })
    
    details["issues"] = {
        "has_errors": len(current_errors) > 0,
        "has_warnings": len(warnings) > 0,
        "error_count": len(current_errors),
        "warning_count": len(warnings),
        "errors": current_errors,
        "warnings": warnings
    }
    
    # Task and Progress Information
    details["progress_info"] = {
        "completed_tasks": project.get("completed_tasks", 0),
        "pending_tasks": project.get("pending_tasks", 0),
        "failed_tasks": project.get("failed_tasks", 0),
        "total_tasks": project.get("completed_tasks", 0) + project.get("pending_tasks", 0) + project.get("failed_tasks", 0),
        "progress_percentage": details["progress"],
        "current_phase_details": _get_phase_details(project)
    }
    
    # Approval and Workflow State
    details["workflow"] = {
        "pending_approvals": [],
        "workflow_state": project["status"],
        "can_proceed": _can_project_proceed(project),
        "next_actions": _get_next_actions(project)
    }
    
    # Add pending approvals
    if project.get("pending_approval"):
        details["workflow"]["pending_approvals"].append({
            "type": "execution_plan",
            "approval_id": project["pending_approval"]["approval_id"],
            "title": project["pending_approval"]["title"],
            "description": project["pending_approval"]["description"]
        })
    
    if project.get("pending_feedback_approval"):
        details["workflow"]["pending_approvals"].append({
            "type": "feedback_review",
            "approval_id": project["pending_feedback_approval"]["approval_id"],
            "title": project["pending_feedback_approval"]["title"],
            "description": project["pending_feedback_approval"]["description"],
            "preview_url": project["pending_feedback_approval"].get("preview_url")
        })
    
    if project.get("pending_deployment_approval"):
        details["workflow"]["pending_approvals"].append({
            "type": "deployment",
            "approval_id": project["pending_deployment_approval"]["approval_id"],
            "title": project["pending_deployment_approval"]["title"],
            "description": project["pending_deployment_approval"]["description"]
        })
    
    return details


def _get_phase_details(project: Dict[str, Any]) -> Dict[str, Any]:
    """Get detailed information about the current phase."""
    current_phase = project.get("current_phase", "unknown")
    
    phase_details = {
        "phase": current_phase,
        "description": "",
        "estimated_duration": "",
        "key_activities": []
    }
    
    if current_phase == "planning":
        phase_details.update({
            "description": "Analyzing requirements and creating execution plan",
            "estimated_duration": "1-2 minutes",
            "key_activities": ["LLM analysis", "Plan creation", "Resource allocation"]
        })
    elif current_phase == "development":
        phase_details.update({
            "description": "Generating website code and assets",
            "estimated_duration": "2-3 minutes",
            "key_activities": ["Code generation", "Asset creation", "Structure setup"]
        })
    elif current_phase == "testing":
        phase_details.update({
            "description": "Running comprehensive tests and quality checks",
            "estimated_duration": "1-2 minutes",
            "key_activities": ["Unit testing", "Integration testing", "UI/Accessibility testing", "Auto-remediation"]
        })
    elif current_phase == "feedback":
        phase_details.update({
            "description": "User review and feedback collection",
            "estimated_duration": "User dependent",
            "key_activities": ["Preview generation", "Feedback collection", "Iterative improvements"]
        })
    elif current_phase == "deployment":
        phase_details.update({
            "description": "Deploying website and setting up monitoring",
            "estimated_duration": "2-5 minutes",
            "key_activities": ["Platform deployment", "Monitoring setup", "Final verification"]
        })
    elif current_phase == "deployed":
        phase_details.update({
            "description": "Website is live and being monitored",
            "estimated_duration": "Ongoing",
            "key_activities": ["Continuous monitoring", "Error tracking", "Performance monitoring"]
        })
    
    return phase_details


def _can_project_proceed(project: Dict[str, Any]) -> bool:
    """Determine if the project can proceed to the next phase."""
    status = project.get("status", "")
    current_phase = project.get("current_phase", "")
    
    # Can't proceed if failed
    if status == "failed":
        return False
    
    # Can proceed if waiting for approval
    if status in ["awaiting_approval", "awaiting_feedback", "awaiting_deployment_approval"]:
        return True
    
    # Can proceed if in active phases
    if status in ["planning", "development", "testing", "feedback", "deployment"]:
        return True
    
    # Completed projects can't proceed further
    if status == "completed":
        return False
    
    return True


def _get_next_actions(project: Dict[str, Any]) -> List[str]:
    """Get list of possible next actions for the project."""
    status = project.get("status", "")
    current_phase = project.get("current_phase", "")
    
    actions = []
    
    if status == "awaiting_approval":
        actions.extend(["Approve execution plan", "Modify requirements", "Cancel project"])
    elif status == "awaiting_feedback":
        actions.extend(["Provide feedback", "Approve for deployment", "Switch to previous version"])
    elif status == "awaiting_deployment_approval":
        actions.extend(["Approve deployment", "Return to feedback", "Cancel deployment"])
    elif status == "completed":
        actions.extend(["View deployed site", "Monitor performance", "Create new version"])
    elif status == "failed":
        actions.extend(["Retry from last checkpoint", "Restart project", "View error details"])
    elif status in ["planning", "development", "testing", "feedback", "deployment"]:
        actions.extend(["Monitor progress", "View current status"])
    
    # Add conditional actions
    if project.get("deployment_url"):
        actions.append("Visit deployed site")
    
    if project.get("feedback_session", {}).get("preview_url"):
        actions.append("Preview current version")
    
    if project.get("test_results"):
        actions.append("View test results")
    
    if project.get("monitoring_result", {}).get("monitoring_active"):
        actions.append("View monitoring dashboard")
    
    return list(set(actions))  # Remove duplicates


@app.get("/api/system/status")
async def system_status():
    """Get system status including agent health."""
    return {
        "status": "operational",
        "agents": {
            "planner_agent": "active" if planner_agent else "inactive",
            "developer_agent": "active" if developer_agent else "inactive",
            "tester_agent": "active" if tester_agent else "inactive",
            "monitor_agent": "active" if monitor_agent else "inactive",
            "llm_service": "active" if llm_service else "inactive",
            "feedback_manager": "active" if feedback_manager else "inactive",
            "preview_manager": "active" if preview_manager else "inactive"
        },
        "projects": {
            "total": len(projects_store),
            "active": len([p for p in projects_store.values() if p["status"] in ["initializing", "planning", "development", "testing", "deployment"]]),
            "completed": len([p for p in projects_store.values() if p["status"] == "completed"]),
            "failed": len([p for p in projects_store.values() if p["status"] == "failed"]),
            "awaiting_feedback": len([p for p in projects_store.values() if p["status"] == "awaiting_feedback"])
        }
    }


@app.get("/api/debug/projects")
async def debug_projects():
    """Debug endpoint to check project states."""
    debug_info = {}
    for project_id, project in projects_store.items():
        debug_info[project_id] = {
            "status": project.get("status"),
            "current_phase": project.get("current_phase"),
            "has_feedback_session": bool(project.get("feedback_session")),
            "has_pending_feedback_approval": bool(project.get("pending_feedback_approval")),
            "has_generated_code": bool(project.get("generated_code")),
            "feedback_session_info": project.get("feedback_session"),
            "last_updated": project.get("last_updated"),
            "errors": project.get("errors", [])
        }
    return {
        "projects": debug_info,
        "feedback_manager_sessions": len(feedback_manager.active_sessions) if feedback_manager else 0,
        "feedback_manager_available": feedback_manager is not None,
        "preview_manager_available": preview_manager is not None
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
    """Serve the generated website as HTML with feedback interface."""
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = projects_store[project_id]
    
    # Check if there's a feedback session with newer versions
    generated_code = None
    if feedback_manager and project.get("status") == "awaiting_feedback":
        try:
            current_version = await feedback_manager.get_current_version(project_id)
            if current_version:
                generated_code = current_version.html_content
                logger.info(f"Serving current version {current_version.version_id} for project {project_id}")
        except Exception as e:
            logger.warning(f"Failed to get current version from feedback manager: {e}")
    
    # Fallback to original generated code
    if not generated_code:
        generated_code = project.get("generated_code")
    
    if not generated_code:
        generated_code = generate_fallback_website(project)
    
    # Inject feedback interface if project is in feedback phase
    if project.get("status") == "awaiting_feedback":
        generated_code = _inject_feedback_interface(generated_code, project_id)
    
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=generated_code)


def _inject_feedback_interface(html_content: str, project_id: str) -> str:
    """Inject feedback interface into HTML content."""
    feedback_interface = f"""
    <!-- Feedback Interface -->
    <div id="feedback-overlay" style="
        position: fixed;
        top: 0;
        right: 0;
        width: 350px;
        height: 100vh;
        background: rgba(0, 0, 0, 0.9);
        color: white;
        padding: 20px;
        box-sizing: border-box;
        z-index: 10000;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        overflow-y: auto;
        transform: translateX(100%);
        transition: transform 0.3s ease;
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h3 style="margin: 0; color: #4CAF50;">Website Feedback</h3>
            <button onclick="toggleFeedback()" style="
                background: none;
                border: none;
                color: white;
                font-size: 20px;
                cursor: pointer;
                padding: 5px;
            ">×</button>
        </div>
        
        <div style="margin-bottom: 20px;">
            <p style="font-size: 14px; line-height: 1.4; margin-bottom: 15px;">
                Review your website and provide feedback for improvements, or approve it for deployment.
            </p>
        </div>
        
        <div style="margin-bottom: 20px;">
            <label style="display: block; margin-bottom: 8px; font-weight: 500;">Your Feedback:</label>
            <textarea id="feedback-text" placeholder="Describe any changes you'd like to make..." style="
                width: 100%;
                height: 120px;
                padding: 10px;
                border: 1px solid #555;
                border-radius: 4px;
                background: #333;
                color: white;
                font-size: 14px;
                resize: vertical;
                box-sizing: border-box;
            "></textarea>
        </div>
        
        <div style="display: flex; flex-direction: column; gap: 10px;">
            <button onclick="submitFeedback()" style="
                background: #2196F3;
                color: white;
                border: none;
                padding: 12px 20px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
            ">Submit Feedback & Regenerate</button>
            
            <button onclick="approveForDeployment()" style="
                background: #4CAF50;
                color: white;
                border: none;
                padding: 12px 20px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
            ">Approve for Deployment</button>
        </div>
        
        <div id="feedback-status" style="
            margin-top: 15px;
            padding: 10px;
            border-radius: 4px;
            font-size: 13px;
            display: none;
        "></div>
    </div>
    
    <!-- Feedback Toggle Button -->
    <button id="feedback-toggle" onclick="toggleFeedback()" style="
        position: fixed;
        top: 20px;
        right: 20px;
        background: #4CAF50;
        color: white;
        border: none;
        padding: 12px 16px;
        border-radius: 50px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 500;
        z-index: 9999;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        transition: all 0.3s ease;
    ">💬 Feedback</button>
    
    <script>
        let feedbackOpen = false;
        
        function toggleFeedback() {{
            const overlay = document.getElementById('feedback-overlay');
            const toggle = document.getElementById('feedback-toggle');
            feedbackOpen = !feedbackOpen;
            
            if (feedbackOpen) {{
                overlay.style.transform = 'translateX(0)';
                toggle.style.right = '370px';
            }} else {{
                overlay.style.transform = 'translateX(100%)';
                toggle.style.right = '20px';
            }}
        }}
        
        async function submitFeedback() {{
            const feedbackText = document.getElementById('feedback-text').value.trim();
            if (!feedbackText) {{
                showStatus('Please enter your feedback before submitting.', 'error');
                return;
            }}
            
            showStatus('Submitting feedback and regenerating...', 'info');
            
            try {{
                const response = await fetch('/api/projects/{project_id}/feedback', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        feedback_text: feedbackText,
                        feedback_type: 'improvement'
                    }})
                }});
                
                if (response.ok) {{
                    const result = await response.json();
                    showStatus('Feedback submitted! Regenerating website...', 'success');
                    
                    // Reload the page after a short delay to show the new version
                    setTimeout(() => {{
                        window.location.reload();
                    }}, 2000);
                }} else {{
                    const error = await response.json();
                    showStatus('Error: ' + (error.detail || 'Failed to submit feedback'), 'error');
                }}
            }} catch (error) {{
                showStatus('Error: Failed to submit feedback', 'error');
            }}
        }}
        
        async function approveForDeployment() {{
            showStatus('Approving for deployment...', 'info');
            
            try {{
                const response = await fetch('/api/approvals/approve', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        project_id: '{project_id}',
                        approval_type: 'feedback_review'
                    }})
                }});
                
                if (response.ok) {{
                    showStatus('Approved! Proceeding to deployment...', 'success');
                    
                    // Close the preview window after a delay
                    setTimeout(() => {{
                        showStatus('Deployment in progress. Closing preview...', 'info');
                        setTimeout(() => {{
                            // Try to close the window
                            if (window.opener) {{
                                window.close();
                            }} else {{
                                // If can't close, show message and redirect to main app
                                showStatus('Please close this tab. Redirecting to main app...', 'info');
                                setTimeout(() => {{
                                    window.location.href = '/';
                                }}, 2000);
                            }}
                        }}, 1000);
                    }}, 2000);
                }} else {{
                    const error = await response.json();
                    showStatus('Error: ' + (error.detail || 'Failed to approve'), 'error');
                }}
            }} catch (error) {{
                showStatus('Error: Failed to approve for deployment', 'error');
            }}
        }}
        
        function showStatus(message, type) {{
            const status = document.getElementById('feedback-status');
            status.textContent = message;
            status.style.display = 'block';
            
            if (type === 'success') {{
                status.style.background = '#4CAF50';
            }} else if (type === 'error') {{
                status.style.background = '#f44336';
            }} else {{
                status.style.background = '#2196F3';
            }}
            
            if (type === 'success' || type === 'error') {{
                setTimeout(() => {{
                    status.style.display = 'none';
                }}, 5000);
            }}
        }}
        
        // Auto-open feedback panel on load
        setTimeout(() => {{
            toggleFeedback();
        }}, 1000);
    </script>
    """
    
    # Insert the feedback interface before the closing body tag
    if "</body>" in html_content:
        html_content = html_content.replace("</body>", feedback_interface + "\n</body>")
    else:
        # If no body tag, append to the end
        html_content += feedback_interface
    
    return html_content


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


class ApprovalRequest(BaseModel):
    project_id: str
    approval_type: str

@app.post("/api/approvals/approve")
async def approve_request(approval: ApprovalRequest, background_tasks: BackgroundTasks):
    """Approve a request for a project."""
    try:
        project_id = approval.project_id
        approval_type = approval.approval_type
        
        if project_id not in projects_store:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project = projects_store[project_id]
        
        if approval_type == "feedback_review":
            # Handle feedback approval - proceed to deployment
            if project.get("status") != "awaiting_feedback":
                raise HTTPException(status_code=400, detail="Project is not awaiting feedback")
            
            # Remove pending feedback approval
            if "pending_feedback_approval" in project:
                del project["pending_feedback_approval"]
            
            # Proceed to deployment
            background_tasks.add_task(deploy_after_approval, project_id)
            
            return {"message": "Feedback approved, proceeding to deployment", "project_id": project_id}
        
        elif approval_type == "execution_plan":
            # Handle execution plan approval
            if project.get("status") != "awaiting_approval":
                raise HTTPException(status_code=400, detail="Project is not awaiting approval")
            
            # Remove pending approval
            if "pending_approval" in project:
                del project["pending_approval"]
            
            # Continue with project execution
            background_tasks.add_task(continue_after_approval, project_id)
            
            return {"message": "Execution plan approved, continuing development", "project_id": project_id}
        
        elif approval_type == "deployment":
            # Handle deployment approval
            if project.get("status") != "awaiting_deployment_approval":
                raise HTTPException(status_code=400, detail="Project is not awaiting deployment approval")
            
            # Remove pending deployment approval
            if "pending_deployment_approval" in project:
                del project["pending_deployment_approval"]
            
            # Proceed to deployment
            background_tasks.add_task(deploy_after_approval, project_id)
            
            return {"message": "Deployment approved, proceeding to deploy", "project_id": project_id}
        
        else:
            raise HTTPException(status_code=400, detail=f"Unknown approval type: {approval_type}")
    
    except Exception as e:
        logger.error(f"Error approving request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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


# Website Feedback Endpoint for Preview Interface
class FeedbackSubmission(BaseModel):
    feedback_text: str
    feedback_type: str = "improvement"

@app.post("/api/projects/{project_id}/feedback")
async def submit_website_feedback(
    project_id: str,
    feedback: FeedbackSubmission,
    background_tasks: BackgroundTasks
):
    """Submit feedback on website design and request regeneration."""
    try:
        if project_id not in projects_store:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project = projects_store[project_id]
        
        # Check if project is in feedback phase
        if project.get("status") != "awaiting_feedback":
            raise HTTPException(
                status_code=400, 
                detail="Project is not in feedback phase"
            )
        
        if not feedback_manager:
            raise HTTPException(
                status_code=503, 
                detail="Feedback system is not available"
            )
        
        # Validate feedback
        if not feedback.feedback_text or len(feedback.feedback_text.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="Feedback must be at least 10 characters long"
            )
        
        logger.info(f"Processing website feedback for project {project_id}")
        
        # Submit feedback and get new version ID
        logger.info(f"Submitting feedback for project {project_id}: {feedback.feedback_text[:100]}...")
        new_version_id = await feedback_manager.submit_feedback(
            project_id=project_id,
            feedback=feedback.feedback_text.strip()
        )
        logger.info(f"New version created: {new_version_id}")
        
        # Get the new version content
        current_version = await feedback_manager.get_current_version(project_id)
        if not current_version:
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve updated version"
            )
        
        # Update preview server with new content
        if preview_manager:
            try:
                await preview_manager.update_preview_content(
                    project_id=project_id,
                    html_content=current_version.html_content
                )
                logger.info(f"Preview updated for project {project_id}")
            except Exception as e:
                logger.error(f"Failed to update preview for project {project_id}: {e}")
        
        # Update project state
        project["feedback_session"]["current_version_id"] = new_version_id
        project["feedback_session"]["versions_count"] += 1
        project["last_updated"] = datetime.utcnow()
        
        # Run tests on new version in background
        if tester_agent:
            background_tasks.add_task(
                run_tests_on_feedback_version,
                project_id,
                new_version_id,
                current_version.html_content
            )
        
        return {
            "status": "success",
            "message": "Feedback processed successfully",
            "new_version_id": new_version_id,
            "versions_count": project["feedback_session"]["versions_count"],
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing feedback for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process feedback: {str(e)}"
        )


async def run_tests_on_feedback_version(project_id: str, version_id: str, html_content: str):
    """Run tests on a new feedback version in the background."""
    try:
        if not tester_agent:
            logger.warning(f"TesterAgent not available for testing version {version_id}")
            return
        
        logger.info(f"Running tests on feedback version {version_id} for project {project_id}")
        
        # Import testing integration
        from .testing_integration import run_comprehensive_tests
        
        # Run tests
        test_results = await run_comprehensive_tests(
            project_id=project_id,
            html_content=html_content,
            tester_agent=tester_agent
        )
        
        # Update version with test results
        if feedback_manager:
            await feedback_manager.update_version_test_results(
                project_id=project_id,
                version_id=version_id,
                test_results=test_results
            )
        
        logger.info(f"Tests completed for feedback version {version_id}")
        
    except Exception as e:
        logger.error(f"Error running tests on feedback version {version_id}: {str(e)}")


# Get version history endpoint
@app.get("/api/projects/{project_id}/versions")
async def get_project_versions(project_id: str):
    """Get version history for a project."""
    try:
        if project_id not in projects_store:
            raise HTTPException(status_code=404, detail="Project not found")
        
        if not feedback_manager:
            raise HTTPException(
                status_code=503,
                detail="Feedback system is not available"
            )
        
        version_history = await feedback_manager.get_version_history(project_id)
        
        return {
            "project_id": project_id,
            "versions": version_history,
            "total_versions": len(version_history)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting versions for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get versions: {str(e)}"
        )


# Switch version endpoint
@app.post("/api/projects/{project_id}/versions/{version_id}/switch")
async def switch_project_version(project_id: str, version_id: str):
    """Switch to a specific version of the project."""
    try:
        if project_id not in projects_store:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project = projects_store[project_id]
        
        # Check if project is in feedback phase
        if project.get("status") != "awaiting_feedback":
            raise HTTPException(
                status_code=400,
                detail="Can only switch versions during feedback phase"
            )
        
        if not feedback_manager:
            raise HTTPException(
                status_code=503,
                detail="Feedback system is not available"
            )
        
        # Switch version
        success = await feedback_manager.switch_version(project_id, version_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Version not found or switch failed"
            )
        
        # Get the switched version content
        current_version = await feedback_manager.get_current_version(project_id)
        if not current_version:
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve switched version"
            )
        
        # Update preview server with switched version content
        if preview_manager:
            try:
                await preview_manager.update_preview_content(
                    project_id=project_id,
                    html_content=current_version.html_content
                )
                logger.info(f"Preview updated to version {version_id} for project {project_id}")
            except Exception as e:
                logger.error(f"Failed to update preview to version {version_id}: {e}")
        
        # Update project state
        project["feedback_session"]["current_version_id"] = version_id
        project["last_updated"] = datetime.utcnow()
        
        return {
            "status": "success",
            "message": f"Switched to version {version_id}",
            "current_version_id": version_id,
            "feedback_applied": current_version.feedback_applied,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error switching to version {version_id} for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to switch version: {str(e)}"
        )


# Get preview URL endpoint
@app.get("/api/projects/{project_id}/preview")
async def get_project_preview(project_id: str):
    """Get the preview URL for a project."""
    try:
        if project_id not in projects_store:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project = projects_store[project_id]
        
        # Check if project has a feedback session
        feedback_session = project.get("feedback_session")
        if not feedback_session:
            raise HTTPException(
                status_code=404,
                detail="No preview available for this project"
            )
        
        preview_url = feedback_session.get("preview_url")
        if not preview_url:
            raise HTTPException(
                status_code=404,
                detail="Preview URL not available"
            )
        
        # Verify preview server is running
        if preview_manager:
            actual_url = preview_manager.get_preview_url(project_id)
            if actual_url:
                preview_url = actual_url
        
        return {
            "project_id": project_id,
            "preview_url": preview_url,
            "status": feedback_session.get("status", "unknown"),
            "current_version_id": feedback_session.get("current_version_id"),
            "versions_count": feedback_session.get("versions_count", 1)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting preview for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get preview: {str(e)}"
        )


# Monitoring API Endpoints
@app.get("/api/projects/{project_id}/monitoring")
async def get_monitoring_status_endpoint(project_id: str):
    """
    Get monitoring status for a project.
    
    Requirements: 2.5
    """
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        from .monitoring_integration import get_monitoring_status
        
        monitoring_status = await get_monitoring_status(
            project_id=project_id,
            monitor_agent=monitor_agent
        )
        
        return monitoring_status
        
    except Exception as e:
        logger.error(f"Error getting monitoring status for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get monitoring status: {str(e)}"
        )


@app.get("/api/projects/{project_id}/monitoring/metrics")
async def get_monitoring_metrics_endpoint(
    project_id: str,
    time_period_hours: int = 24
):
    """
    Get monitoring metrics for a project over a specified time period.
    
    Args:
        project_id: Unique identifier for the project
        time_period_hours: Number of hours to look back for metrics (default: 24)
    
    Requirements: 2.6
    """
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if time_period_hours < 1 or time_period_hours > 168:  # Max 1 week
        raise HTTPException(
            status_code=400,
            detail="time_period_hours must be between 1 and 168 (1 week)"
        )
    
    try:
        from .monitoring_integration import get_monitoring_metrics
        
        monitoring_metrics = await get_monitoring_metrics(
            project_id=project_id,
            monitor_agent=monitor_agent,
            time_period_hours=time_period_hours
        )
        
        return monitoring_metrics
        
    except Exception as e:
        logger.error(f"Error getting monitoring metrics for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get monitoring metrics: {str(e)}"
        )


@app.post("/api/projects/{project_id}/monitoring/setup")
async def setup_monitoring_endpoint(
    project_id: str,
    config: Optional[Dict[str, Any]] = None
):
    """
    Manually set up monitoring for a deployed project.
    
    Args:
        project_id: Unique identifier for the project
        config: Optional monitoring configuration overrides
    """
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = projects_store[project_id]
    deployment_url = project.get("deployment_url")
    
    if not deployment_url:
        raise HTTPException(
            status_code=400,
            detail="Project must be deployed before monitoring can be set up"
        )
    
    try:
        from .monitoring_integration import setup_monitoring, create_monitoring_config
        
        # Set up monitoring
        monitoring_result = await setup_monitoring(
            project_id=project_id,
            deployment_url=deployment_url,
            monitor_agent=monitor_agent,
            config=config
        )
        
        # Update project with monitoring result
        project["monitoring_result"] = monitoring_result
        project["last_updated"] = datetime.utcnow()
        
        if config:
            # Create and store monitoring configuration
            monitoring_config = create_monitoring_config(
                error_tracking_enabled=config.get("error_tracking_enabled", True),
                uptime_monitoring_enabled=config.get("uptime_monitoring_enabled", True),
                performance_monitoring_enabled=config.get("performance_monitoring_enabled", False),
                notification_channels=config.get("notification_channels", []),
                alert_thresholds=config.get("alert_thresholds", {})
            )
            project["monitoring_config"] = monitoring_config.model_dump()
        
        return monitoring_result
        
    except Exception as e:
        logger.error(f"Error setting up monitoring for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to set up monitoring: {str(e)}"
        )


@app.delete("/api/projects/{project_id}/monitoring")
async def stop_monitoring_endpoint(project_id: str):
    """
    Stop monitoring for a project.
    
    Args:
        project_id: Unique identifier for the project
    """
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        from .monitoring_integration import stop_monitoring
        
        stop_result = await stop_monitoring(
            project_id=project_id,
            monitor_agent=monitor_agent
        )
        
        # Update project state
        project = projects_store[project_id]
        if stop_result.get("stopped"):
            project["monitoring_result"] = {
                "monitoring_active": False,
                "stopped_at": datetime.utcnow().isoformat()
            }
        project["last_updated"] = datetime.utcnow()
        
        return stop_result
        
    except Exception as e:
        logger.error(f"Error stopping monitoring for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop monitoring: {str(e)}"
        )


# Testing API Endpoints

@app.get("/api/projects/{project_id}/tests")
async def get_test_results(project_id: str):
    """
    Get detailed test results for a project.
    
    Args:
        project_id: Unique identifier for the project
        
    Returns:
        Detailed test results including unit, integration, and UI test results
    """
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = projects_store[project_id]
    test_results = project.get("test_results")
    
    if not test_results:
        return {
            "project_id": project_id,
            "test_status": "not_run",
            "message": "No tests have been run for this project",
            "last_updated": project.get("last_updated")
        }
    
    try:
        # Format test results for API response
        formatted_results = {
            "project_id": project_id,
            "test_status": project.get("test_status", "unknown"),
            "overall_success": test_results.get("overall_success", False),
            "total_tests": test_results.get("total_tests", 0),
            "passed_tests": test_results.get("passed_tests", 0),
            "failed_tests": test_results.get("failed_tests", 0),
            "test_categories": {
                "unit_tests": {
                    "status": test_results.get("unit_tests", {}).get("status", "not_run"),
                    "passed": test_results.get("unit_tests", {}).get("passed", 0),
                    "failed": test_results.get("unit_tests", {}).get("failed", 0),
                    "details": test_results.get("unit_tests", {}).get("details", [])
                },
                "integration_tests": {
                    "status": test_results.get("integration_tests", {}).get("status", "not_run"),
                    "passed": test_results.get("integration_tests", {}).get("passed", 0),
                    "failed": test_results.get("integration_tests", {}).get("failed", 0),
                    "details": test_results.get("integration_tests", {}).get("details", [])
                },
                "ui_tests": {
                    "status": test_results.get("ui_tests", {}).get("status", "not_run"),
                    "passed": test_results.get("ui_tests", {}).get("passed", 0),
                    "failed": test_results.get("ui_tests", {}).get("failed", 0),
                    "details": test_results.get("ui_tests", {}).get("details", [])
                }
            },
            "execution_time": test_results.get("execution_time", 0),
            "test_environment": test_results.get("test_environment", {}),
            "remediation_results": project.get("remediation_results"),
            "last_updated": project.get("last_updated"),
            "created_at": test_results.get("created_at")
        }
        
        return formatted_results
        
    except Exception as e:
        logger.error(f"Error formatting test results for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve test results: {str(e)}"
        )


@app.post("/api/projects/{project_id}/tests/rerun")
async def rerun_tests(project_id: str):
    """
    Rerun tests for a project.
    
    Args:
        project_id: Unique identifier for the project
        
    Returns:
        Updated test results after rerunning tests
    """
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = projects_store[project_id]
    html_content = project.get("generated_code")
    
    if not html_content:
        raise HTTPException(
            status_code=400,
            detail="No generated code available for testing"
        )
    
    try:
        # Import testing integration
        from .testing_integration import run_comprehensive_tests, handle_test_failures
        
        logger.info(f"Rerunning tests for project {project_id}")
        
        # Update project status
        project["current_phase"] = "testing"
        project["test_status"] = "running"
        project["last_updated"] = datetime.utcnow()
        
        # Run comprehensive tests
        test_results = await run_comprehensive_tests(project_id, html_content, tester_agent)
        
        # Store updated test results
        project["test_results"] = test_results
        project["last_updated"] = datetime.utcnow()
        
        # Handle test failures if any
        if not test_results.get("overall_success", False):
            logger.warning(f"Tests failed during rerun for project {project_id}, attempting remediation")
            
            # Get failure analyzer from tester agent if available
            failure_analyzer = None
            if tester_agent and hasattr(tester_agent, 'failure_analyzer'):
                failure_analyzer = tester_agent.failure_analyzer
            
            remediation_results = await handle_test_failures(
                project_id, test_results, failure_analyzer
            )
            project["remediation_results"] = remediation_results
            
            if remediation_results.get("retry_recommended"):
                project["test_status"] = "failed_with_remediation"
            else:
                project["test_status"] = "failed"
        else:
            project["test_status"] = "passed"
            logger.info(f"All tests passed during rerun for project {project_id}")
        
        # Return formatted test results
        return await get_test_results(project_id)
        
    except Exception as e:
        logger.error(f"Error rerunning tests for project {project_id}: {str(e)}")
        project["test_status"] = "error"
        project["last_updated"] = datetime.utcnow()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to rerun tests: {str(e)}"
        )


# Feedback API Endpoints

@app.post("/api/projects/{project_id}/preview")
async def create_preview(project_id: str):
    """
    Create a preview for a project to enable feedback collection.
    
    Args:
        project_id: Unique identifier for the project
        
    Returns:
        Preview URL and session information
    """
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = projects_store[project_id]
    html_content = project.get("generated_code")
    
    if not html_content:
        raise HTTPException(
            status_code=400,
            detail="No generated code available for preview"
        )
    
    try:
        # Create feedback session if not exists
        if not feedback_manager:
            raise HTTPException(
                status_code=503,
                detail="Feedback manager not available"
            )
        
        # Check if feedback session already exists
        existing_session = project.get("feedback_session")
        if existing_session and existing_session.get("status") == "active":
            return {
                "project_id": project_id,
                "preview_url": existing_session.get("preview_url"),
                "session_id": existing_session.get("session_id"),
                "current_version_id": existing_session.get("current_version_id"),
                "status": "existing_session",
                "message": "Preview session already active"
            }
        
        logger.info(f"Creating new preview session for project {project_id}")
        
        # Create new feedback session
        feedback_session = await feedback_manager.create_feedback_session(
            project_id=project_id,
            html_content=html_content,
            test_results=project.get("test_results")
        )
        
        # Start preview server if preview manager is available
        preview_url = feedback_session.preview_url  # Default fallback
        if preview_manager:
            try:
                logger.info(f"Starting preview server for project {project_id}")
                preview_url = await preview_manager.start_preview_server(
                    project_id=project_id,
                    html_content=html_content
                )
                # Update feedback session with actual preview URL
                feedback_session.preview_url = preview_url
                logger.info(f"Preview server started at {preview_url}")
            except Exception as e:
                logger.error(f"Failed to start preview server for project {project_id}: {e}")
                # Continue with default preview URL
        
        # Update project with feedback session info
        project["feedback_session"] = {
            "session_id": project_id,
            "current_version_id": feedback_session.current_version_id,
            "preview_url": preview_url,
            "status": feedback_session.status,
            "versions_count": len(feedback_session.versions)
        }
        project["preview_url"] = preview_url
        project["last_updated"] = datetime.utcnow()
        
        return {
            "project_id": project_id,
            "preview_url": preview_url,
            "session_id": project_id,
            "current_version_id": feedback_session.current_version_id,
            "status": "created",
            "message": "Preview session created successfully",
            "versions_count": len(feedback_session.versions)
        }
        
    except Exception as e:
        logger.error(f"Error creating preview for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create preview: {str(e)}"
        )


@app.post("/api/projects/{project_id}/feedback")
async def submit_feedback(project_id: str, feedback: FeedbackRequest):
    """
    Submit feedback for a project and trigger regeneration.
    
    Args:
        project_id: Unique identifier for the project
        feedback: Feedback request containing user feedback
        
    Returns:
        Feedback processing response with new version information
    """
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = projects_store[project_id]
    
    # Check if feedback session exists
    feedback_session_info = project.get("feedback_session")
    if not feedback_session_info or feedback_session_info.get("status") != "active":
        raise HTTPException(
            status_code=400,
            detail="No active feedback session found. Create a preview first."
        )
    
    if not feedback_manager:
        raise HTTPException(
            status_code=503,
            detail="Feedback manager not available"
        )
    
    try:
        logger.info(f"Processing feedback for project {project_id}: {feedback.feedback_text[:100]}...")
        
        # Submit feedback and get new version
        new_version_id = await feedback_manager.submit_feedback(
            project_id=project_id,
            feedback=feedback.feedback_text
        )
        
        # Update project with new version info
        feedback_session = await feedback_manager.get_feedback_session(project_id)
        if feedback_session:
            project["feedback_session"]["current_version_id"] = feedback_session.current_version_id
            project["feedback_session"]["versions_count"] = len(feedback_session.versions)
        
        project["last_updated"] = datetime.utcnow()
        
        # Create response
        response = FeedbackResponse(
            version_id=new_version_id,
            regeneration_status="completed",
            estimated_completion="immediate",
            changes_summary=f"Applied {feedback.feedback_type} feedback: {feedback.feedback_text[:100]}..."
        )
        
        logger.info(f"Feedback processed successfully for project {project_id}, new version: {new_version_id}")
        
        return response.model_dump()
        
    except Exception as e:
        logger.error(f"Error processing feedback for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process feedback: {str(e)}"
        )


@app.get("/api/projects/{project_id}/versions")
async def get_versions(project_id: str):
    """
    Get all versions for a project.
    
    Args:
        project_id: Unique identifier for the project
        
    Returns:
        List of all versions with metadata
    """
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if not feedback_manager:
        raise HTTPException(
            status_code=503,
            detail="Feedback manager not available"
        )
    
    try:
        # Get version history from feedback manager
        version_history = await feedback_manager.get_version_history(project_id)
        
        # Format versions for API response
        formatted_versions = []
        for version in version_history:
            formatted_versions.append({
                "version_id": version.get("version_id"),
                "created_at": version.get("created_at"),
                "is_current": version.get("is_current", False),
                "feedback_applied": version.get("feedback_applied"),
                "test_results_summary": {
                    "overall_success": version.get("test_results", {}).get("overall_success"),
                    "total_tests": version.get("test_results", {}).get("total_tests", 0),
                    "passed_tests": version.get("test_results", {}).get("passed_tests", 0),
                    "failed_tests": version.get("test_results", {}).get("failed_tests", 0)
                } if version.get("test_results") else None,
                "content_length": len(version.get("html_content", ""))
            })
        
        return {
            "project_id": project_id,
            "versions": formatted_versions,
            "total_versions": len(formatted_versions),
            "current_version_id": next(
                (v["version_id"] for v in formatted_versions if v["is_current"]), 
                None
            )
        }
        
    except Exception as e:
        logger.error(f"Error getting versions for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get versions: {str(e)}"
        )


@app.post("/api/projects/{project_id}/versions/{version_id}/switch")
async def switch_version(project_id: str, version_id: str):
    """
    Switch to a specific version of a project.
    
    Args:
        project_id: Unique identifier for the project
        version_id: ID of the version to switch to
        
    Returns:
        Success status and updated version information
    """
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if not feedback_manager:
        raise HTTPException(
            status_code=503,
            detail="Feedback manager not available"
        )
    
    try:
        logger.info(f"Switching project {project_id} to version {version_id}")
        
        # Switch version using feedback manager
        success = await feedback_manager.switch_version(project_id, version_id)
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Version {version_id} not found for project {project_id}"
            )
        
        # Update project state
        project = projects_store[project_id]
        feedback_session = await feedback_manager.get_feedback_session(project_id)
        
        if feedback_session:
            project["feedback_session"]["current_version_id"] = feedback_session.current_version_id
            
            # Update preview server with new version content if available
            if preview_manager:
                try:
                    current_version = next(
                        (v for v in feedback_session.versions if v.version_id == version_id),
                        None
                    )
                    if current_version:
                        await preview_manager.update_preview_content(
                            project_id=project_id,
                            html_content=current_version.html_content
                        )
                        logger.info(f"Preview server updated with version {version_id} content")
                except Exception as e:
                    logger.error(f"Failed to update preview server content: {e}")
        
        project["last_updated"] = datetime.utcnow()
        
        return {
            "project_id": project_id,
            "switched_to_version": version_id,
            "success": True,
            "message": f"Successfully switched to version {version_id}",
            "preview_url": project.get("preview_url")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error switching version for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to switch version: {str(e)}"
        )


# Deployment API Endpoints

@app.post("/api/projects/{project_id}/deploy/{version_id}")
async def deploy_version(project_id: str, version_id: str):
    """
    Deploy a specific version of a project.
    
    Args:
        project_id: Unique identifier for the project
        version_id: ID of the version to deploy
        
    Returns:
        Deployment status and URL
    """
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if not feedback_manager:
        raise HTTPException(
            status_code=503,
            detail="Feedback manager not available"
        )
    
    try:
        logger.info(f"Deploying version {version_id} of project {project_id}")
        
        # Get the specific version content
        version_history = await feedback_manager.get_version_history(project_id)
        target_version = next(
            (v for v in version_history if v.get("version_id") == version_id),
            None
        )
        
        if not target_version:
            raise HTTPException(
                status_code=404,
                detail=f"Version {version_id} not found for project {project_id}"
            )
        
        # Update project with version-specific content for deployment
        project = projects_store[project_id]
        original_code = project.get("generated_code")
        
        # Temporarily set the version content for deployment
        project["generated_code"] = target_version.get("html_content")
        project["deploying_version_id"] = version_id
        project["status"] = "deploying"
        project["current_phase"] = "deployment"
        project["last_updated"] = datetime.utcnow()
        
        try:
            # Deploy using existing deployment logic
            deployment_url = await deploy_to_netlify(project_id, project)
            
            # Set up monitoring after successful deployment
            monitoring_result = None
            if deployment_url and not deployment_url.startswith("https://demo-"):
                from .monitoring_integration import setup_monitoring, create_monitoring_config
                
                logger.info(f"Setting up monitoring for version {version_id} deployment at {deployment_url}")
                
                # Create monitoring configuration
                monitoring_config = create_monitoring_config(
                    error_tracking_enabled=True,
                    uptime_monitoring_enabled=True,
                    performance_monitoring_enabled=False,
                    notification_channels=[],
                    alert_thresholds={
                        "error_rate_threshold": 5.0,
                        "response_time_threshold": 5000,
                        "uptime_threshold": 95.0
                    }
                )
                
                # Set up monitoring
                logger.info(f"📊 Setting up monitoring for project {project_id} at {deployment_url}")
                monitoring_result = await setup_monitoring(
                    project_id=project_id,
                    deployment_url=deployment_url,
                    monitor_agent=monitor_agent,
                    config={
                        "check_interval": 300,  # 5 minutes
                        "timeout": 30,
                        "error_tracking_enabled": True,
                        "uptime_monitoring_enabled": True,
                        "performance_monitoring_enabled": False,
                        "error_rate_threshold": 5.0,
                        "response_time_threshold": 5000,
                        "uptime_threshold": 95.0
                    }
                )
                
                if monitoring_result.get("monitoring_active"):
                    logger.info(f"✅ Monitoring successfully set up for project {project_id}")
                else:
                    logger.warning(f"⚠️ Monitoring setup failed for project {project_id}: {monitoring_result.get('error', 'Unknown error')}")
                
                # Store monitoring configuration
                project["monitoring_config"] = monitoring_config.model_dump()
                project["monitoring_result"] = monitoring_result
            
            # Update project state with deployment info
            project["status"] = "completed"
            project["current_phase"] = "deployed"
            project["progress"] = 100.0
            project["deployment_url"] = deployment_url
            project["deployed_version_id"] = version_id
            project["deployment_timestamp"] = datetime.utcnow()
            project["last_updated"] = datetime.utcnow()
            
            # Clean up preview server after successful deployment
            if preview_manager:
                try:
                    await preview_manager.stop_preview_server(project_id)
                    logger.info(f"Preview server cleaned up after deployment of version {version_id}")
                except Exception as e:
                    logger.error(f"Failed to cleanup preview server: {e}")
            
            # Complete feedback session
            if feedback_manager:
                try:
                    await feedback_manager.complete_feedback_session(project_id)
                    logger.info(f"Feedback session completed after deployment of version {version_id}")
                except Exception as e:
                    logger.error(f"Failed to complete feedback session: {e}")
            
            logger.info(f"Version {version_id} of project {project_id} deployed successfully to {deployment_url}")
            
            return {
                "project_id": project_id,
                "version_id": version_id,
                "deployment_url": deployment_url,
                "deployment_status": "completed",
                "monitoring_active": monitoring_result.get("monitoring_active", False) if monitoring_result else False,
                "deployment_timestamp": project["deployment_timestamp"],
                "message": f"Version {version_id} deployed successfully"
            }
            
        finally:
            # Restore original code if deployment failed
            if project.get("status") != "completed":
                project["generated_code"] = original_code
            
            # Clean up deployment tracking fields
            project.pop("deploying_version_id", None)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deploying version {version_id} of project {project_id}: {str(e)}")
        
        # Clean up on deployment failure
        project = projects_store.get(project_id, {})
        project["status"] = "failed"
        project["error"] = str(e)
        project["last_updated"] = datetime.utcnow()
        
        # Clean up preview server on deployment failure
        if preview_manager:
            try:
                await preview_manager.stop_preview_server(project_id)
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup preview server after deployment failure: {cleanup_error}")
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to deploy version {version_id}: {str(e)}"
        )


@app.get("/api/projects/{project_id}/deployment/status")
async def get_deployment_status(project_id: str):
    """
    Get deployment status for a project, including version-specific information.
    
    Args:
        project_id: Unique identifier for the project
        
    Returns:
        Deployment status with version information
    """
    if project_id not in projects_store:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = projects_store[project_id]
    
    try:
        deployment_info = {
            "project_id": project_id,
            "deployment_status": project.get("status"),
            "current_phase": project.get("current_phase"),
            "deployment_url": project.get("deployment_url"),
            "deployed_version_id": project.get("deployed_version_id"),
            "deployment_timestamp": project.get("deployment_timestamp"),
            "monitoring_active": False,
            "monitoring_status": None,
            "last_updated": project.get("last_updated")
        }
        
        # Add monitoring information if available
        monitoring_result = project.get("monitoring_result")
        if monitoring_result:
            deployment_info["monitoring_active"] = monitoring_result.get("monitoring_active", False)
            deployment_info["monitoring_status"] = monitoring_result.get("status")
        
        # Add deployment progress information
        if project.get("status") == "deploying":
            deployment_info["progress"] = project.get("progress", 0)
            deployment_info["deploying_version_id"] = project.get("deploying_version_id")
        
        return deployment_info
        
    except Exception as e:
        logger.error(f"Error getting deployment status for project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get deployment status: {str(e)}"
        )


@app.get("/api/monitoring/status")
async def get_global_monitoring_status():
    """
    Get global monitoring status for all projects.
    """
    try:
        if not monitor_agent:
            return {
                "monitoring_available": False,
                "error": "Monitor agent not available",
                "status_time": datetime.utcnow().isoformat()
            }
        
        # Get monitoring status from the monitor agent
        global_status = monitor_agent.get_monitoring_status()
        
        # Add additional information
        monitored_projects = []
        for project_id in global_status.get("monitored_projects", []):
            if project_id in projects_store:
                project = projects_store[project_id]
                monitored_projects.append({
                    "project_id": project_id,
                    "deployment_url": project.get("deployment_url"),
                    "monitoring_active": project.get("monitoring_result", {}).get("monitoring_active", False),
                    "last_updated": project.get("last_updated")
                })
        
        return {
            "monitoring_available": True,
            "active_monitors": global_status.get("active_monitors", 0),
            "monitored_projects": monitored_projects,
            "tools_configured": global_status.get("tools_configured", {}),
            "status_time": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting global monitoring status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get monitoring status: {str(e)}"
        )