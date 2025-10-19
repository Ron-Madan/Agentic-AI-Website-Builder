"""Test configuration and fixtures."""

import pytest
from fastapi.testclient import TestClient

from src.agentic_web_app_builder.api.main import app
from src.agentic_web_app_builder.core.config import get_settings, update_settings


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def test_settings():
    """Create test settings."""
    original_settings = get_settings()
    
    # Update settings for testing
    update_settings(
        environment="testing",
        database_url="sqlite:///./test_agentic_web_app_builder.db"
    )
    
    yield get_settings()
    
    # Restore original settings
    update_settings(**original_settings.dict())