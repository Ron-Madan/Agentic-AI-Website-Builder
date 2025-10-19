"""Configuration management for the agentic web app builder."""

from typing import Optional, Dict, Any
from pydantic import Field
from pydantic_settings import BaseSettings
from enum import Enum


class Environment(str, Enum):
    """Environment types."""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class DatabaseConfig(BaseSettings):
    """Database configuration."""
    url: str = Field(default="sqlite:///./agentic_web_app_builder.db")
    echo: bool = Field(default=False)
    pool_size: int = Field(default=10)
    max_overflow: int = Field(default=20)
    
    class Config:
        env_prefix = "DB_"


class RedisConfig(BaseSettings):
    """Redis configuration."""
    host: str = Field(default="localhost")
    port: int = Field(default=6379)
    db: int = Field(default=0)
    password: Optional[str] = Field(default=None)
    decode_responses: bool = Field(default=True)
    
    class Config:
        env_prefix = "REDIS_"


class APIConfig(BaseSettings):
    """API configuration."""
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    debug: bool = Field(default=False)
    secret_key: str = Field(default="your-secret-key-change-in-production")
    access_token_expire_minutes: int = Field(default=30)
    
    class Config:
        env_prefix = "API_"


class LLMConfig(BaseSettings):
    """LLM provider configuration."""
    openai_api_key: Optional[str] = Field(default=None)
    anthropic_api_key: Optional[str] = Field(default=None)
    default_model: str = Field(default="gpt-4")
    max_tokens: int = Field(default=4000)
    temperature: float = Field(default=0.7)
    
    class Config:
        env_prefix = "LLM_"


class DeploymentConfig(BaseSettings):
    """Deployment platform configuration."""
    netlify_access_token: Optional[str] = Field(default=None)
    vercel_access_token: Optional[str] = Field(default=None)
    default_platform: str = Field(default="netlify")
    
    class Config:
        env_prefix = "DEPLOY_"


class MonitoringConfig(BaseSettings):
    """Monitoring configuration."""
    sentry_dsn: Optional[str] = Field(default=None)
    slack_webhook_url: Optional[str] = Field(default=None)
    email_smtp_server: Optional[str] = Field(default=None)
    email_smtp_port: int = Field(default=587)
    email_username: Optional[str] = Field(default=None)
    email_password: Optional[str] = Field(default=None)
    
    class Config:
        env_prefix = "MONITOR_"


class Settings(BaseSettings):
    """Main application settings."""
    environment: Environment = Field(default=Environment.DEVELOPMENT)
    app_name: str = Field(default="Agentic Web App Builder")
    version: str = Field(default="0.1.0")
    
    # Agent configuration
    max_concurrent_tasks: int = Field(default=5)
    task_timeout_minutes: int = Field(default=30)
    checkpoint_interval_minutes: int = Field(default=10)
    
    # LLM Configuration
    llm_openai_api_key: Optional[str] = Field(default=None)
    llm_anthropic_api_key: Optional[str] = Field(default=None)
    llm_default_model: str = Field(default="gpt-4")
    llm_max_tokens: int = Field(default=4000)
    llm_temperature: float = Field(default=0.7)
    
    # Deployment Configuration
    netlify_access_token: Optional[str] = Field(default=None)
    vercel_access_token: Optional[str] = Field(default=None)
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }
    
    def get_database_url(self) -> str:
        """Get the database URL based on environment."""
        if self.environment == Environment.TESTING:
            return "sqlite:///./test_agentic_web_app_builder.db"
        return "sqlite:///./agentic_web_app_builder.db"
    
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == Environment.DEVELOPMENT
    
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == Environment.PRODUCTION


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings


def update_settings(**kwargs: Any) -> None:
    """Update global settings."""
    global settings
    for key, value in kwargs.items():
        if hasattr(settings, key):
            setattr(settings, key, value)