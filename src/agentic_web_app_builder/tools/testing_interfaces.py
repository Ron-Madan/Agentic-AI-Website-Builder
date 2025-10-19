"""Testing tool interfaces for the tester agent."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from enum import Enum
from datetime import datetime

from pydantic import BaseModel, Field

from ..core.interfaces import ToolInterface


class TestType(Enum):
    """Types of tests that can be executed."""
    UNIT = "unit"
    INTEGRATION = "integration"
    UI = "ui"
    PERFORMANCE = "performance"
    ACCESSIBILITY = "accessibility"
    VISUAL_REGRESSION = "visual_regression"


class TestStatus(Enum):
    """Status of test execution."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class TestFailure(BaseModel):
    """Model for test failure information."""
    
    test_name: str = Field(..., description="Name of the failed test")
    error_message: str = Field(..., description="Error message from the test")
    stack_trace: Optional[str] = Field(None, description="Stack trace of the failure")
    file_path: Optional[str] = Field(None, description="File path where the test failed")
    line_number: Optional[int] = Field(None, description="Line number where the test failed")
    expected: Optional[str] = Field(None, description="Expected value")
    actual: Optional[str] = Field(None, description="Actual value")
    category: Optional[str] = Field(None, description="Failure category for auto-remediation")


class TestResults(BaseModel):
    """Model for test execution results."""
    
    test_suite: str = Field(..., description="Name of the test suite")
    test_type: TestType = Field(..., description="Type of tests executed")
    total_tests: int = Field(..., description="Total number of tests")
    passed: int = Field(..., description="Number of passed tests")
    failed: int = Field(..., description="Number of failed tests")
    skipped: int = Field(..., description="Number of skipped tests")
    errors: int = Field(default=0, description="Number of tests with errors")
    duration: float = Field(..., description="Test execution duration in seconds")
    coverage: Optional[float] = Field(None, description="Code coverage percentage")
    failures: List[TestFailure] = Field(default_factory=list, description="List of test failures")
    warnings: List[str] = Field(default_factory=list, description="List of warnings")
    executed_at: datetime = Field(default_factory=datetime.utcnow, description="Test execution timestamp")
    
    @property
    def success_rate(self) -> float:
        """Calculate test success rate."""
        if self.total_tests == 0:
            return 0.0
        return (self.passed / self.total_tests) * 100.0
    
    @property
    def is_successful(self) -> bool:
        """Check if all tests passed."""
        return self.failed == 0 and self.errors == 0


class UITestResults(TestResults):
    """Extended test results for UI testing."""
    
    screenshots: List[str] = Field(default_factory=list, description="Paths to captured screenshots")
    accessibility_violations: List[Dict[str, Any]] = Field(default_factory=list, description="Accessibility violations found")
    performance_metrics: Dict[str, float] = Field(default_factory=dict, description="Performance metrics")
    visual_diffs: List[str] = Field(default_factory=list, description="Visual regression differences")


class TestConfig(BaseModel):
    """Configuration for test execution."""
    
    project_path: str = Field(..., description="Path to the project to test")
    test_type: TestType = Field(..., description="Type of tests to run")
    test_patterns: List[str] = Field(default_factory=list, description="Test file patterns to include")
    exclude_patterns: List[str] = Field(default_factory=list, description="Test file patterns to exclude")
    timeout: int = Field(default=300, description="Test timeout in seconds")
    parallel: bool = Field(default=True, description="Whether to run tests in parallel")
    coverage: bool = Field(default=True, description="Whether to collect coverage")
    environment: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    browser: Optional[str] = Field(None, description="Browser for UI tests")
    headless: bool = Field(default=True, description="Whether to run browser tests headless")
    viewport: Optional[Dict[str, int]] = Field(None, description="Viewport size for UI tests")


class UnitTestTool(ToolInterface):
    """Abstract interface for unit testing tools."""
    
    @abstractmethod
    async def run_tests(self, config: TestConfig) -> TestResults:
        """Run unit tests with the given configuration."""
        pass
    
    @abstractmethod
    async def generate_test_files(self, source_files: List[str]) -> Dict[str, str]:
        """Generate test files for given source files."""
        pass
    
    @abstractmethod
    async def analyze_coverage(self, project_path: str) -> Dict[str, Any]:
        """Analyze test coverage for the project."""
        pass
    
    async def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a unit testing command."""
        if command == "run_tests":
            config = TestConfig(**parameters.get("config", {}))
            result = await self.run_tests(config)
            return {"test_results": result.dict()}
        
        elif command == "generate_tests":
            source_files = parameters.get("source_files", [])
            result = await self.generate_test_files(source_files)
            return {"generated_tests": result}
        
        elif command == "analyze_coverage":
            project_path = parameters.get("project_path", ".")
            result = await self.analyze_coverage(project_path)
            return {"coverage_analysis": result}
        
        else:
            raise ValueError(f"Unknown unit test command: {command}")


class IntegrationTestTool(ToolInterface):
    """Abstract interface for integration testing tools."""
    
    @abstractmethod
    async def run_integration_tests(self, config: TestConfig) -> TestResults:
        """Run integration tests with the given configuration."""
        pass
    
    @abstractmethod
    async def setup_test_environment(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Set up the test environment for integration tests."""
        pass
    
    @abstractmethod
    async def teardown_test_environment(self, environment_id: str) -> bool:
        """Tear down the test environment."""
        pass
    
    async def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an integration testing command."""
        if command == "run_tests":
            config = TestConfig(**parameters.get("config", {}))
            result = await self.run_integration_tests(config)
            return {"test_results": result.dict()}
        
        elif command == "setup_environment":
            config = parameters.get("config", {})
            result = await self.setup_test_environment(config)
            return {"environment": result}
        
        elif command == "teardown_environment":
            environment_id = parameters.get("environment_id")
            result = await self.teardown_test_environment(environment_id)
            return {"teardown_success": result}
        
        else:
            raise ValueError(f"Unknown integration test command: {command}")


class UITestTool(ToolInterface):
    """Abstract interface for UI testing tools."""
    
    @abstractmethod
    async def run_ui_tests(self, config: TestConfig, deployment_url: str) -> UITestResults:
        """Run UI tests against a deployed application."""
        pass
    
    @abstractmethod
    async def capture_screenshots(self, url: str, selectors: List[str]) -> List[str]:
        """Capture screenshots of specific elements."""
        pass
    
    @abstractmethod
    async def run_accessibility_tests(self, url: str) -> List[Dict[str, Any]]:
        """Run accessibility tests on the application."""
        pass
    
    @abstractmethod
    async def run_visual_regression_tests(self, url: str, baseline_dir: str) -> List[str]:
        """Run visual regression tests against baseline images."""
        pass
    
    async def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a UI testing command."""
        if command == "run_tests":
            config = TestConfig(**parameters.get("config", {}))
            deployment_url = parameters.get("deployment_url", "")
            result = await self.run_ui_tests(config, deployment_url)
            return {"test_results": result.dict()}
        
        elif command == "capture_screenshots":
            url = parameters.get("url", "")
            selectors = parameters.get("selectors", [])
            result = await self.capture_screenshots(url, selectors)
            return {"screenshots": result}
        
        elif command == "accessibility_tests":
            url = parameters.get("url", "")
            result = await self.run_accessibility_tests(url)
            return {"accessibility_violations": result}
        
        elif command == "visual_regression":
            url = parameters.get("url", "")
            baseline_dir = parameters.get("baseline_dir", "")
            result = await self.run_visual_regression_tests(url, baseline_dir)
            return {"visual_diffs": result}
        
        else:
            raise ValueError(f"Unknown UI test command: {command}")


class TestFailureAnalyzer(ABC):
    """Abstract interface for analyzing test failures."""
    
    @abstractmethod
    async def analyze_failure(self, failure: TestFailure, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a test failure and suggest remediation."""
        pass
    
    @abstractmethod
    async def categorize_failure(self, failure: TestFailure) -> str:
        """Categorize the type of test failure."""
        pass
    
    @abstractmethod
    async def suggest_fix(self, failure: TestFailure, category: str) -> Optional[str]:
        """Suggest an automatic fix for the failure."""
        pass
    
    @abstractmethod
    async def apply_fix(self, failure: TestFailure, fix: str, project_path: str) -> bool:
        """Apply an automatic fix to the codebase."""
        pass