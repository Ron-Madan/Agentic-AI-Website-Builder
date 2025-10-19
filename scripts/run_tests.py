#!/usr/bin/env python3
"""Test runner script."""

import subprocess
import sys


def main():
    """Run tests with coverage."""
    cmd = [
        "python", "-m", "pytest",
        "tests/",
        "-v",
        "--cov=src/agentic_web_app_builder",
        "--cov-report=html",
        "--cov-report=term-missing"
    ]
    
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()