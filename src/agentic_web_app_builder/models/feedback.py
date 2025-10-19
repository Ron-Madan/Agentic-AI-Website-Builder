"""Feedback-related data models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, validator


class FeedbackRequest(BaseModel):
    """Model for user feedback requests."""
    
    feedback_text: str = Field(..., min_length=10, description="User feedback text describing desired changes")
    feedback_type: str = Field(default="general", description="Type of feedback: design, content, functionality, general")
    priority: int = Field(default=1, ge=1, le=5, description="Feedback priority from 1 (low) to 5 (high)")
    
    @validator('feedback_text')
    def feedback_text_not_empty(cls, v: str) -> str:
        """Validate that feedback text is not empty and has meaningful content."""
        if not v.strip():
            raise ValueError('Feedback text cannot be empty')
        if len(v.strip()) < 10:
            raise ValueError('Feedback text must be at least 10 characters long')
        return v.strip()
    
    @validator('feedback_type')
    def feedback_type_valid(cls, v: str) -> str:
        """Validate that feedback type is one of the allowed values."""
        allowed_types = ["design", "content", "functionality", "general"]
        if v.lower() not in allowed_types:
            raise ValueError(f'Feedback type must be one of: {", ".join(allowed_types)}')
        return v.lower()


class FeedbackResponse(BaseModel):
    """Model for feedback processing responses."""
    
    version_id: str = Field(..., description="ID of the new version created from feedback")
    regeneration_status: str = Field(..., description="Status of the regeneration process")
    estimated_completion: str = Field(..., description="Estimated completion time for regeneration")
    changes_summary: Optional[str] = Field(None, description="Summary of changes made based on feedback")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Response creation timestamp")
    
    @validator('regeneration_status')
    def regeneration_status_valid(cls, v: str) -> str:
        """Validate that regeneration status is one of the allowed values."""
        allowed_statuses = ["pending", "in_progress", "completed", "failed"]
        if v.lower() not in allowed_statuses:
            raise ValueError(f'Regeneration status must be one of: {", ".join(allowed_statuses)}')
        return v.lower()