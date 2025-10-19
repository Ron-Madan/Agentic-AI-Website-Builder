"""Feedback loop management system for handling user feedback and website iterations."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from uuid import uuid4

from ..tools.llm_service import LLMService, LLMRequest, LLMMessage
from ..models.base import BaseModelWithTimestamp
from ..core.state_manager import StateManager


logger = logging.getLogger(__name__)


@dataclass
class ProjectVersion:
    """Represents a version of a project with its content and metadata."""
    
    version_id: str
    html_content: str
    feedback_applied: Optional[str]
    test_results: Optional[Dict[str, Any]]
    created_at: datetime
    is_current: bool


@dataclass
class FeedbackSession:
    """Represents an active feedback session for a project."""
    
    project_id: str
    versions: List[ProjectVersion]
    current_version_id: str
    preview_url: str
    status: str  # "active", "completed", "cancelled"


class FeedbackLoopManager:
    """Manages the feedback loop process for website iterations."""
    
    def __init__(self, llm_service: Optional[LLMService] = None, state_manager: Optional[StateManager] = None):
        """Initialize the feedback loop manager.
        
        Args:
            llm_service: LLM service for processing feedback and regeneration
            state_manager: State manager for persisting feedback sessions
        """
        self.llm_service = llm_service or LLMService()
        self.state_manager = state_manager or StateManager()
        self.active_sessions: Dict[str, FeedbackSession] = {}
        
    async def create_feedback_session(self, project_id: str, html_content: str, test_results: Optional[Dict[str, Any]] = None) -> FeedbackSession:
        """Create a new feedback session for a project.
        
        Args:
            project_id: ID of the project
            html_content: Initial HTML content of the website
            test_results: Optional test results for the initial version
            
        Returns:
            FeedbackSession: The created feedback session
        """
        logger.info(f"Creating feedback session for project {project_id}")
        
        # Create initial version
        initial_version = ProjectVersion(
            version_id=str(uuid4()),
            html_content=html_content,
            feedback_applied=None,
            test_results=test_results,
            created_at=datetime.utcnow(),
            is_current=True
        )
        
        # Create feedback session
        session = FeedbackSession(
            project_id=project_id,
            versions=[initial_version],
            current_version_id=initial_version.version_id,
            preview_url=f"http://localhost:8080/preview/{project_id}",  # Will be updated by PreviewManager
            status="active"
        )
        
        # Store session
        self.active_sessions[project_id] = session
        
        # Persist session state
        await self._persist_session(session)
        
        logger.info(f"Feedback session created for project {project_id} with version {initial_version.version_id}")
        return session
    
    async def submit_feedback(self, project_id: str, feedback: str) -> str:
        """Submit user feedback and trigger regeneration.
        
        Args:
            project_id: ID of the project
            feedback: User feedback text
            
        Returns:
            str: ID of the new version created from feedback
            
        Raises:
            ValueError: If no active session exists for the project
        """
        logger.info(f"Submitting feedback for project {project_id}")
        
        session = self.active_sessions.get(project_id)
        if not session or session.status != "active":
            raise ValueError(f"No active feedback session found for project {project_id}")
        
        # Get current version
        current_version = self._get_version_by_id(session, session.current_version_id)
        if not current_version:
            raise ValueError(f"Current version {session.current_version_id} not found")
        
        # Generate new version with feedback applied
        new_html_content = await self.regenerate_with_feedback(
            current_version.html_content, 
            feedback
        )
        
        # Create new version
        new_version = ProjectVersion(
            version_id=str(uuid4()),
            html_content=new_html_content,
            feedback_applied=feedback,
            test_results=None,  # Will be populated after testing
            created_at=datetime.utcnow(),
            is_current=True
        )
        
        # Mark previous version as not current
        current_version.is_current = False
        
        # Add new version to session
        session.versions.append(new_version)
        session.current_version_id = new_version.version_id
        
        # Persist updated session
        await self._persist_session(session)
        
        logger.info(f"New version {new_version.version_id} created for project {project_id}")
        return new_version.version_id
    
    async def regenerate_with_feedback(self, html_content: str, feedback: str) -> str:
        """Use LLM to regenerate HTML content based on user feedback.
        
        Args:
            html_content: Current HTML content
            feedback: User feedback to apply
            
        Returns:
            str: Regenerated HTML content
        """
        logger.info("Regenerating HTML content with LLM based on feedback")
        
        system_prompt = """You are an expert web developer tasked with modifying HTML content based on user feedback.

Your job is to:
1. Analyze the current HTML content
2. Understand the user's feedback and requested changes
3. Modify the HTML to incorporate the feedback while maintaining:
   - Valid HTML structure
   - Existing functionality
   - Good web development practices
   - Responsive design principles

Return only the modified HTML content, without any explanations or markdown formatting."""
        
        user_prompt = f"""Please modify the following HTML content based on the user feedback:

Current HTML Content:
{html_content}

User Feedback:
{feedback}

Please provide the updated HTML content that incorporates the requested changes."""
        
        request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt)
            ],
            temperature=0.7  # Balanced creativity and consistency
        )
        
        try:
            response = await self.llm_service.generate(request)
            regenerated_content = response.content.strip()
            
            # Basic validation - ensure we got HTML content
            if not regenerated_content or not regenerated_content.startswith('<'):
                logger.warning("LLM response doesn't appear to be valid HTML, using original content")
                return html_content
            
            return regenerated_content
            
        except Exception as e:
            logger.error(f"Error regenerating content with LLM: {str(e)}")
            # Return original content if regeneration fails
            return html_content
    
    async def get_version_history(self, project_id: str) -> List[Dict[str, Any]]:
        """Get version history for a project.
        
        Args:
            project_id: ID of the project
            
        Returns:
            List[Dict]: List of version information
        """
        session = self.active_sessions.get(project_id)
        if not session:
            return []
        
        return [
            {
                "version_id": version.version_id,
                "feedback_applied": version.feedback_applied,
                "created_at": version.created_at.isoformat(),
                "is_current": version.is_current,
                "has_test_results": version.test_results is not None
            }
            for version in session.versions
        ]
    
    async def switch_version(self, project_id: str, version_id: str) -> bool:
        """Switch to a specific version of the project.
        
        Args:
            project_id: ID of the project
            version_id: ID of the version to switch to
            
        Returns:
            bool: True if switch was successful, False otherwise
        """
        logger.info(f"Switching project {project_id} to version {version_id}")
        
        session = self.active_sessions.get(project_id)
        if not session:
            logger.error(f"No session found for project {project_id}")
            return False
        
        # Find the target version
        target_version = self._get_version_by_id(session, version_id)
        if not target_version:
            logger.error(f"Version {version_id} not found for project {project_id}")
            return False
        
        # Mark all versions as not current
        for version in session.versions:
            version.is_current = False
        
        # Mark target version as current
        target_version.is_current = True
        session.current_version_id = version_id
        
        # Persist updated session
        await self._persist_session(session)
        
        logger.info(f"Successfully switched project {project_id} to version {version_id}")
        return True
    
    async def get_current_version(self, project_id: str) -> Optional[ProjectVersion]:
        """Get the current version of a project.
        
        Args:
            project_id: ID of the project
            
        Returns:
            Optional[ProjectVersion]: Current version or None if not found
        """
        session = self.active_sessions.get(project_id)
        if not session:
            return None
        
        return self._get_version_by_id(session, session.current_version_id)
    
    async def update_version_test_results(self, project_id: str, version_id: str, test_results: Dict[str, Any]) -> bool:
        """Update test results for a specific version.
        
        Args:
            project_id: ID of the project
            version_id: ID of the version
            test_results: Test results to store
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        session = self.active_sessions.get(project_id)
        if not session:
            return False
        
        version = self._get_version_by_id(session, version_id)
        if not version:
            return False
        
        version.test_results = test_results
        await self._persist_session(session)
        
        logger.info(f"Updated test results for project {project_id} version {version_id}")
        return True
    
    async def complete_feedback_session(self, project_id: str) -> bool:
        """Mark a feedback session as completed.
        
        Args:
            project_id: ID of the project
            
        Returns:
            bool: True if session was completed successfully
        """
        session = self.active_sessions.get(project_id)
        if not session:
            return False
        
        session.status = "completed"
        await self._persist_session(session)
        
        logger.info(f"Feedback session completed for project {project_id}")
        return True
    
    async def cancel_feedback_session(self, project_id: str) -> bool:
        """Cancel an active feedback session.
        
        Args:
            project_id: ID of the project
            
        Returns:
            bool: True if session was cancelled successfully
        """
        session = self.active_sessions.get(project_id)
        if not session:
            return False
        
        session.status = "cancelled"
        await self._persist_session(session)
        
        logger.info(f"Feedback session cancelled for project {project_id}")
        return True
    
    def _get_version_by_id(self, session: FeedbackSession, version_id: str) -> Optional[ProjectVersion]:
        """Get a version by its ID from a session.
        
        Args:
            session: The feedback session
            version_id: ID of the version to find
            
        Returns:
            Optional[ProjectVersion]: The version if found, None otherwise
        """
        for version in session.versions:
            if version.version_id == version_id:
                return version
        return None
    
    async def _persist_session(self, session: FeedbackSession) -> None:
        """Persist a feedback session to storage.
        
        Args:
            session: The feedback session to persist
        """
        try:
            # Convert session to dict for storage
            session_data = {
                "project_id": session.project_id,
                "current_version_id": session.current_version_id,
                "preview_url": session.preview_url,
                "status": session.status,
                "versions": [
                    {
                        "version_id": v.version_id,
                        "html_content": v.html_content,
                        "feedback_applied": v.feedback_applied,
                        "test_results": v.test_results,
                        "created_at": v.created_at.isoformat(),
                        "is_current": v.is_current
                    }
                    for v in session.versions
                ]
            }
            
            # Store in state manager
            await self.state_manager.store_data(
                f"feedback_session_{session.project_id}",
                session_data
            )
            
        except Exception as e:
            logger.error(f"Failed to persist feedback session for project {session.project_id}: {str(e)}")
    
    async def load_session(self, project_id: str) -> Optional[FeedbackSession]:
        """Load a feedback session from storage.
        
        Args:
            project_id: ID of the project
            
        Returns:
            Optional[FeedbackSession]: The loaded session or None if not found
        """
        try:
            session_data = await self.state_manager.get_data(f"feedback_session_{project_id}")
            if not session_data:
                return None
            
            # Convert stored data back to session
            versions = [
                ProjectVersion(
                    version_id=v["version_id"],
                    html_content=v["html_content"],
                    feedback_applied=v["feedback_applied"],
                    test_results=v["test_results"],
                    created_at=datetime.fromisoformat(v["created_at"]),
                    is_current=v["is_current"]
                )
                for v in session_data["versions"]
            ]
            
            session = FeedbackSession(
                project_id=session_data["project_id"],
                versions=versions,
                current_version_id=session_data["current_version_id"],
                preview_url=session_data["preview_url"],
                status=session_data["status"]
            )
            
            # Add to active sessions if still active
            if session.status == "active":
                self.active_sessions[project_id] = session
            
            return session
            
        except Exception as e:
            logger.error(f"Failed to load feedback session for project {project_id}: {str(e)}")
            return None
    
    async def get_feedback_session(self, project_id: str) -> Optional[FeedbackSession]:
        """Get an active feedback session for a project.
        
        Args:
            project_id: ID of the project
            
        Returns:
            Optional[FeedbackSession]: The active session or None if not found
        """
        # Check active sessions first
        if project_id in self.active_sessions:
            return self.active_sessions[project_id]
        
        # Try to load from storage
        session = await self.load_session(project_id)
        if session and session.status == "active":
            self.active_sessions[project_id] = session
            return session
        
        return None