"""Project-related data models."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

from .base import BaseModelWithTimestamp, Phase, TaskStatus, TaskType


class ProjectRequest(BaseModelWithTimestamp):
    """Model for user project requests."""
    
    user_id: str = Field(..., description="ID of the user making the request")
    description: str = Field(..., description="Natural language description of the project")
    requirements: List[str] = Field(default_factory=list, description="List of specific requirements")
    preferences: Dict[str, Any] = Field(default_factory=dict, description="User preferences and configuration")
    
    @validator('description')
    def description_not_empty(cls, v: str) -> str:
        """Validate that description is not empty."""
        if not v.strip():
            raise ValueError('Description cannot be empty')
        return v.strip()
    
    @validator('user_id')
    def user_id_not_empty(cls, v: str) -> str:
        """Validate that user_id is not empty."""
        if not v.strip():
            raise ValueError('User ID cannot be empty')
        return v.strip()


class Task(BaseModelWithTimestamp):
    """Model for individual tasks within a project."""
    
    project_id: str = Field(..., description="ID of the project this task belongs to")
    type: TaskType = Field(..., description="Type of task")
    description: str = Field(..., description="Detailed description of the task")
    dependencies: List[str] = Field(default_factory=list, description="List of task IDs this task depends on")
    estimated_duration: Optional[timedelta] = Field(None, description="Estimated time to complete the task")
    actual_duration: Optional[timedelta] = Field(None, description="Actual time taken to complete the task")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current status of the task")
    agent_assigned: Optional[str] = Field(None, description="ID of the agent assigned to this task")
    result: Optional[Dict[str, Any]] = Field(None, description="Task execution result data")
    error_message: Optional[str] = Field(None, description="Error message if task failed")
    retry_count: int = Field(default=0, description="Number of times this task has been retried")
    max_retries: int = Field(default=3, description="Maximum number of retries allowed")
    
    @validator('description')
    def description_not_empty(cls, v: str) -> str:
        """Validate that description is not empty."""
        if not v.strip():
            raise ValueError('Task description cannot be empty')
        return v.strip()
    
    @validator('retry_count')
    def retry_count_valid(cls, v: int, values: Dict[str, Any]) -> int:
        """Validate retry count is within limits."""
        max_retries = values.get('max_retries', 3)
        if v < 0:
            raise ValueError('Retry count cannot be negative')
        if v > max_retries:
            raise ValueError(f'Retry count cannot exceed max_retries ({max_retries})')
        return v
    
    def can_retry(self) -> bool:
        """Check if the task can be retried."""
        return self.retry_count < self.max_retries and self.status == TaskStatus.FAILED
    
    def mark_completed(self, result: Optional[Dict[str, Any]] = None) -> None:
        """Mark the task as completed with optional result data."""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.error_message = None
        self.update_timestamp()
    
    def mark_failed(self, error_message: str) -> None:
        """Mark the task as failed with error message."""
        self.status = TaskStatus.FAILED
        self.error_message = error_message
        self.retry_count += 1
        self.update_timestamp()


class FileMetadata(BaseModel):
    """Metadata for generated files."""
    
    path: str = Field(..., description="File path relative to project root")
    size: int = Field(..., description="File size in bytes")
    checksum: str = Field(..., description="File checksum for integrity verification")
    content_type: str = Field(..., description="MIME type of the file")
    generated_by: str = Field(..., description="Agent that generated this file")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DeploymentInfo(BaseModel):
    """Information about project deployment."""
    
    url: str = Field(..., description="Deployed application URL")
    platform: str = Field(..., description="Deployment platform (e.g., 'netlify', 'vercel')")
    deployment_id: str = Field(..., description="Platform-specific deployment ID")
    status: str = Field(..., description="Current deployment status")
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    environment: str = Field(default="production", description="Deployment environment")
    build_logs: Optional[List[str]] = Field(None, description="Build and deployment logs")
    
    @validator('url')
    def url_format(cls, v: str) -> str:
        """Validate URL format."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v


class MonitoringConfig(BaseModel):
    """Configuration for application monitoring."""
    
    error_tracking_enabled: bool = Field(default=True, description="Whether error tracking is enabled")
    uptime_monitoring_enabled: bool = Field(default=True, description="Whether uptime monitoring is enabled")
    performance_monitoring_enabled: bool = Field(default=False, description="Whether performance monitoring is enabled")
    notification_channels: List[str] = Field(default_factory=list, description="List of notification channels")
    alert_thresholds: Dict[str, Any] = Field(default_factory=dict, description="Alert threshold configurations")
    monitoring_services: Dict[str, str] = Field(default_factory=dict, description="External monitoring service configurations")


class ProjectStructure(BaseModel):
    """Model for project structure information."""
    
    name: str = Field(..., description="Project name")
    template: str = Field(..., description="Template used for generation")
    directories: List[str] = Field(default_factory=list, description="List of directories created")
    files: List[str] = Field(default_factory=list, description="List of files created")
    dependencies: Dict[str, str] = Field(default_factory=dict, description="Project dependencies")
    scripts: Dict[str, str] = Field(default_factory=dict, description="Build and run scripts")
    configuration: Dict[str, Any] = Field(default_factory=dict, description="Project configuration")


class ComponentSpecs(BaseModel):
    """Specifications for generating code components."""
    
    component_name: str = Field(..., description="Name of the component")
    component_type: str = Field(..., description="Type of component (e.g., 'react-component', 'page', 'service')")
    props: Dict[str, Any] = Field(default_factory=dict, description="Component properties and types")
    styling: Dict[str, Any] = Field(default_factory=dict, description="Styling specifications")
    functionality: List[str] = Field(default_factory=list, description="List of required functionality")
    dependencies: List[str] = Field(default_factory=list, description="Component dependencies")


class CodeFiles(BaseModel):
    """Model for generated code files."""
    
    files: Dict[str, str] = Field(..., description="Mapping of file paths to file contents")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata about generated files")
    dependencies_added: List[str] = Field(default_factory=list, description="New dependencies that were added")
    imports_updated: List[str] = Field(default_factory=list, description="Import statements that were updated")


class Repository(BaseModel):
    """Model for Git repository information."""
    
    path: str = Field(..., description="Local path to the repository")
    remote_url: Optional[str] = Field(None, description="Remote repository URL")
    current_branch: str = Field(default="main", description="Current active branch")
    last_commit: Optional[str] = Field(None, description="Hash of the last commit")
    status: str = Field(default="clean", description="Repository status")
    branches: List[str] = Field(default_factory=list, description="List of available branches")


class DeploymentConfig(BaseModel):
    """Configuration for application deployment."""
    
    platform: str = Field(..., description="Deployment platform (netlify, vercel, etc.)")
    project_path: str = Field(..., description="Path to the project to deploy")
    build_command: Optional[str] = Field(None, description="Build command to run")
    output_directory: Optional[str] = Field(None, description="Output directory for built files")
    environment_variables: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    domain: Optional[str] = Field(None, description="Custom domain for deployment")
    branch: str = Field(default="main", description="Git branch to deploy")


class DeploymentResult(BaseModel):
    """Result of a deployment operation."""
    
    deployment_id: str = Field(..., description="Unique deployment identifier")
    url: str = Field(..., description="URL of the deployed application")
    status: str = Field(..., description="Deployment status")
    build_logs: List[str] = Field(default_factory=list, description="Build and deployment logs")
    deployed_at: datetime = Field(default_factory=datetime.utcnow, description="Deployment timestamp")
    platform: str = Field(..., description="Platform where the app was deployed")
    version: Optional[str] = Field(None, description="Version or commit hash deployed")


class ProjectVersion(BaseModel):
    """Model for project version information."""
    
    version_id: str = Field(..., description="Unique version identifier")
    html_content: str = Field(..., description="HTML content for this version")
    feedback_applied: Optional[str] = Field(None, description="Feedback that was applied to create this version")
    test_results: Optional[Dict[str, Any]] = Field(None, description="Test results for this version")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Version creation timestamp")
    is_current: bool = Field(default=False, description="Whether this is the current active version")


class FeedbackSession(BaseModel):
    """Model for feedback session information."""
    
    project_id: str = Field(..., description="ID of the project this session belongs to")
    versions: List[ProjectVersion] = Field(default_factory=list, description="List of all versions in this session")
    current_version_id: str = Field(..., description="ID of the currently active version")
    preview_url: Optional[str] = Field(None, description="URL for previewing the current version")
    status: str = Field(default="active", description="Session status: active, completed, cancelled")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Session creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Session last update timestamp")


class ProjectState(BaseModelWithTimestamp):
    """Complete state of a project."""
    
    project_id: str = Field(..., description="Unique project identifier")
    request: ProjectRequest = Field(..., description="Original project request")
    current_phase: Phase = Field(default=Phase.PLANNING, description="Current project phase")
    completed_tasks: List[Task] = Field(default_factory=list, description="List of completed tasks")
    pending_tasks: List[Task] = Field(default_factory=list, description="List of pending tasks")
    failed_tasks: List[Task] = Field(default_factory=list, description="List of failed tasks")
    generated_files: List[FileMetadata] = Field(default_factory=list, description="List of generated files")
    deployment_info: Optional[DeploymentInfo] = Field(None, description="Deployment information")
    monitoring_config: Optional[MonitoringConfig] = Field(None, description="Monitoring configuration")
    checkpoints: List[str] = Field(default_factory=list, description="List of checkpoint IDs")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional project metadata")
    
    # New fields for testing, monitoring, and feedback
    test_results: Optional[Dict[str, Any]] = Field(None, description="Latest test execution results")
    feedback_session: Optional[FeedbackSession] = Field(None, description="Current feedback session information")
    versions: List[ProjectVersion] = Field(default_factory=list, description="List of all project versions")
    current_version_id: Optional[str] = Field(None, description="ID of the currently active version")
    preview_url: Optional[str] = Field(None, description="URL for previewing the current version")
    
    def get_all_tasks(self) -> List[Task]:
        """Get all tasks regardless of status."""
        return self.completed_tasks + self.pending_tasks + self.failed_tasks
    
    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        """Get a task by its ID."""
        for task in self.get_all_tasks():
            if task.id == task_id:
                return task
        return None
    
    def add_task(self, task: Task) -> None:
        """Add a new task to the project."""
        if task.status == TaskStatus.COMPLETED:
            self.completed_tasks.append(task)
        elif task.status == TaskStatus.FAILED:
            self.failed_tasks.append(task)
        else:
            self.pending_tasks.append(task)
        self.update_timestamp()
    
    def update_task_status(self, task_id: str, new_status: TaskStatus) -> bool:
        """Update the status of a task and move it to the appropriate list."""
        task = self.get_task_by_id(task_id)
        if not task:
            return False
        
        # Remove from current list
        if task in self.completed_tasks:
            self.completed_tasks.remove(task)
        elif task in self.pending_tasks:
            self.pending_tasks.remove(task)
        elif task in self.failed_tasks:
            self.failed_tasks.remove(task)
        
        # Update status and add to appropriate list
        task.status = new_status
        task.update_timestamp()
        
        if new_status == TaskStatus.COMPLETED:
            self.completed_tasks.append(task)
        elif new_status == TaskStatus.FAILED:
            self.failed_tasks.append(task)
        else:
            self.pending_tasks.append(task)
        
        self.update_timestamp()
        return True
    
    def get_progress_percentage(self) -> float:
        """Calculate project completion percentage."""
        total_tasks = len(self.get_all_tasks())
        if total_tasks == 0:
            return 0.0
        return (len(self.completed_tasks) / total_tasks) * 100.0