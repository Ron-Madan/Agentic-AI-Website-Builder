#!/usr/bin/env python3
"""Development server runner."""

import uvicorn
from src.agentic_web_app_builder.core.config import get_settings
from src.agentic_web_app_builder.utils.logging import setup_logging


def main():
    """Run the development server."""
    setup_logging()
    settings = get_settings()
    
    uvicorn.run(
        "src.agentic_web_app_builder.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )


if __name__ == "__main__":
    main()