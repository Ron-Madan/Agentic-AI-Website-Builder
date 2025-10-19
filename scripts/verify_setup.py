#!/usr/bin/env python3
"""Verify the project setup is working correctly."""

import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def verify_imports():
    """Verify all core imports work correctly."""
    try:
        # Test core interfaces
        from agentic_web_app_builder.core.interfaces import (
            BaseAgent, StateManager, ToolInterface, ErrorHandler,
            Task, AgentEvent, ProjectRequest, TaskStatus, TaskType, Phase, EventType
        )
        print("✓ Core interfaces imported successfully")
        
        # Test configuration
        from agentic_web_app_builder.core.config import Settings, get_settings
        settings = get_settings()
        print(f"✓ Configuration loaded successfully - Environment: {settings.environment}")
        
        # Test agent base classes
        from agentic_web_app_builder.agents.base import AgentBase
        print("✓ Agent base classes imported successfully")
        
        # Test API
        from agentic_web_app_builder.api.main import app
        print("✓ FastAPI app created successfully")
        
        return True
        
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def verify_project_structure():
    """Verify the project structure is correct."""
    required_dirs = [
        'src/agentic_web_app_builder',
        'src/agentic_web_app_builder/core',
        'src/agentic_web_app_builder/agents',
        'src/agentic_web_app_builder/api',
        'src/agentic_web_app_builder/models',
        'src/agentic_web_app_builder/tools',
        'src/agentic_web_app_builder/utils',
        'tests',
        'scripts'
    ]
    
    required_files = [
        'pyproject.toml',
        'README.md',
        '.env',
        '.env.example',
        '.gitignore',
        'Makefile'
    ]
    
    all_good = True
    
    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"✓ Directory exists: {dir_path}")
        else:
            print(f"✗ Directory missing: {dir_path}")
            all_good = False
    
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✓ File exists: {file_path}")
        else:
            print(f"✗ File missing: {file_path}")
            all_good = False
    
    return all_good

def main():
    """Main verification function."""
    print("🔍 Verifying Agentic Web App Builder Setup")
    print("=" * 50)
    
    print("\n📁 Checking project structure...")
    structure_ok = verify_project_structure()
    
    print("\n📦 Checking imports...")
    imports_ok = verify_imports()
    
    print("\n" + "=" * 50)
    if structure_ok and imports_ok:
        print("🎉 Setup verification completed successfully!")
        print("✅ All core components are working correctly")
        print("\n🚀 You can now start development with:")
        print("   make dev  # Start development server")
        print("   make test # Run tests")
        return 0
    else:
        print("❌ Setup verification failed!")
        print("Please check the errors above and fix them.")
        return 1

if __name__ == "__main__":
    sys.exit(main())