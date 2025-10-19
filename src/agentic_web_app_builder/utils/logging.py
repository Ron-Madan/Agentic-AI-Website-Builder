"""Logging utilities."""

import logging
import sys
from typing import Optional
from ..core.config import get_settings


def setup_logging(level: Optional[str] = None) -> None:
    """Setup application logging."""
    settings = get_settings()
    
    if level is None:
        level = "DEBUG" if settings.is_development() else "INFO"
    
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Set specific logger levels
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)