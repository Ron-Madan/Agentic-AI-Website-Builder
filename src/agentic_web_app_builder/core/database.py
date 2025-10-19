"""Database models and setup for the agentic web app builder."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import TypeDecorator, VARCHAR

from .config import get_settings

Base = declarative_base()


class JSONType(TypeDecorator):
    """Custom SQLAlchemy type for JSON data."""
    
    impl = VARCHAR
    cache_ok = True
    
    def process_bind_param(self, value: Any, dialect: Any) -> Optional[str]:
        """Convert Python object to JSON string."""
        if value is not None:
            return json.dumps(value)
        return value
    
    def process_result_value(self, value: Any, dialect: Any) -> Any:
        """Convert JSON string to Python object."""
        if value is not None:
            return json.loads(value)
        return value


class ProjectRequestDB(Base):
    """Database model for project requests."""
    
    __tablename__ = "project_requests"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=False)
    requirements = Column(JSONType, nullable=False, default=list)
    preferences = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class TaskDB(Base):
    """Database model for tasks."""
    
    __tablename__ = "tasks"
    
    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    type = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    dependencies = Column(JSONType, nullable=False, default=list)
    estimated_duration_seconds = Column(Integer, nullable=True)
    actual_duration_seconds = Column(Integer, nullable=True)
    status = Column(String, nullable=False, default="pending")
    agent_assigned = Column(String, nullable=True)
    result = Column(JSONType, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ProjectStateDB(Base):
    """Database model for project state."""
    
    __tablename__ = "project_states"
    
    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, unique=True, index=True)
    current_phase = Column(String, nullable=False, default="planning")
    generated_files = Column(JSONType, nullable=False, default=list)
    deployment_info = Column(JSONType, nullable=True)
    monitoring_config = Column(JSONType, nullable=True)
    checkpoints = Column(JSONType, nullable=False, default=list)
    project_metadata = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AgentEventDB(Base):
    """Database model for agent events."""
    
    __tablename__ = "agent_events"
    
    id = Column(String, primary_key=True)
    event_id = Column(String, nullable=False, unique=True, index=True)
    source_agent = Column(String, nullable=False, index=True)
    target_agents = Column(JSONType, nullable=True)
    event_type = Column(String, nullable=False, index=True)
    payload = Column(JSONType, nullable=False, default=dict)
    project_id = Column(String, nullable=True, index=True)
    task_id = Column(String, nullable=True, index=True)
    priority = Column(Integer, nullable=False, default=5)
    expires_at = Column(DateTime, nullable=True)
    processed = Column(Boolean, nullable=False, default=False)
    processing_results = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class EventSubscriptionDB(Base):
    """Database model for event subscriptions."""
    
    __tablename__ = "event_subscriptions"
    
    id = Column(String, primary_key=True)
    subscriber_id = Column(String, nullable=False, index=True)
    subscription_name = Column(String, nullable=False)
    filter_criteria = Column(JSONType, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    callback_url = Column(String, nullable=True)
    delivery_mode = Column(String, nullable=False, default="queue")
    max_queue_size = Column(Integer, nullable=False, default=1000)
    retry_policy = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CheckpointDB(Base):
    """Database model for project checkpoints."""
    
    __tablename__ = "checkpoints"
    
    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    checkpoint_name = Column(String, nullable=True)
    state_snapshot = Column(JSONType, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# Database setup
def create_database_engine():
    """Create database engine based on configuration."""
    settings = get_settings()
    database_url = settings.get_database_url()
    
    engine = create_engine(
        database_url,
        echo=settings.is_development(),
        pool_pre_ping=True,
    )
    
    return engine


def create_session_factory():
    """Create session factory for database operations."""
    engine = create_database_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_database():
    """Initialize database tables."""
    engine = create_database_engine()
    Base.metadata.create_all(bind=engine)


# Global session factory
SessionLocal = create_session_factory()


def get_db_session():
    """Get database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()