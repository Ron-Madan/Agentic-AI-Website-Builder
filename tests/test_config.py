"""Test configuration management."""

import pytest
from src.agentic_web_app_builder.core.config import Settings, Environment


def test_settings_creation():
    """Test settings creation with defaults."""
    settings = Settings()
    assert settings.environment == Environment.DEVELOPMENT
    assert settings.app_name == "Agentic Web App Builder"
    assert settings.version == "0.1.0"


def test_database_url_by_environment():
    """Test database URL changes based on environment."""
    settings = Settings(environment=Environment.TESTING)
    assert "test_" in settings.get_database_url()
    
    settings = Settings(environment=Environment.DEVELOPMENT)
    assert "test_" not in settings.get_database_url()


def test_environment_checks():
    """Test environment check methods."""
    dev_settings = Settings(environment=Environment.DEVELOPMENT)
    assert dev_settings.is_development() is True
    assert dev_settings.is_production() is False
    
    prod_settings = Settings(environment=Environment.PRODUCTION)
    assert prod_settings.is_development() is False
    assert prod_settings.is_production() is True