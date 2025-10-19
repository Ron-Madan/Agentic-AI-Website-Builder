"""Tester Agent implementation for automated testing."""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..agents.base import TesterAgentBase
from ..core.interfaces import Task, EventType, TaskType
from ..models.project import ProjectState
from ..tools.testing_interfaces import (
    TestType, TestConfig, TestResults, UITestResults, TestFailure,
    UnitTestTool, IntegrationTestTool, UITestTool, TestFailureAnalyzer
)


logger = logging.getLogger(__name__)


class TesterAgent(TesterAgentBase):
    """Agent responsible for automated testing of web applications."""
    
    def __init__(self, state_manager: 'StateManager'):
        super().__init__(state_manager)
        self.unit_test_tool: Optional[UnitTestTool] = None
        self.integration_test_tool: Optional[IntegrationTestTool] = None
        self.ui_test_tool: Optional[UITestTool] = None
        self.failure_analyzer: Optional[TestFailureAnalyzer] = None
        self._test_results_cache: Dict[str, TestResults] = {}
        
        # Register event handlers
        self.register_event_handler(EventType.DEPLOYMENT_READY, self._handle_deployment_ready)
        self.register_event_handler(EventType.TASK_COMPLETED, self._handle_task_completed)
    
    def set_tools(self, 
                  unit_test_tool: UnitTestTool,
                  integration_test_tool: IntegrationTestTool,
                  ui_test_tool: UITestTool,
                  failure_analyzer: TestFailureAnalyzer) -> None:
        """Set the testing tools for the agent."""
        self.unit_test_tool = unit_test_tool
        self.integration_test_tool = integration_test_tool
        self.ui_test_tool = ui_test_tool
        self.failure_analyzer = failure_analyzer
        self.logger.info("Testing tools configured successfully")
    
    async def _execute_task_impl(self, task: Task) -> Dict[str, Any]:
        """Execute testing tasks."""
        self.logger.info(f"Executing testing task: {task.description}")
        
        if task.type != TaskType.TESTING:
            raise ValueError(f"Invalid task type for TesterAgent: {task.type}")
        
        # Get project state
        project_id = task.id.split("_")[0]
        project_state_data = await self.state_manager.get_project_state(project_id)
        if not project_state_data:
            raise ValueError(f"Project state not found for project {project_id}")
        
        # Determine test type from task metadata
        test_type_str = task.metadata.get("test_type", "unit") if task.metadata else "unit"
        test_type = TestType(test_type_str)
        
        # Execute appropriate test type
        if test_type == TestType.UNIT:
            return await self._run_unit_tests(project_state_data, task)
        elif test_type == TestType.INTEGRATION:
            return await self._run_integration_tests(project_state_data, task)
        elif test_type == TestType.UI:
            return await self._run_ui_tests(project_state_data, task)
        else:
            raise ValueError(f"Unsupported test type: {test_type}")
    
    async def _run_unit_tests(self, project_state_data: Dict[str, Any], task: Task) -> Dict[str, Any]:
        """Run unit tests for the project."""
        if not self.unit_test_tool:
            raise ValueError("Unit test tool not configured")
        
        self.logger.info("Running unit tests")
        
        # Extract project path from state
        project_path = project_state_data.get("metadata", {}).get("project_path", ".")
        
        # Configure unit tests
        config = TestConfig(
            project_path=project_path,
            test_type=TestType.UNIT,
            test_patterns=["**/*.test.js", "**/*.test.ts", "**/*.spec.js", "**/*.spec.ts"],
            timeout=300,
            parallel=True,
            coverage=True
        )
        
        try:
            # Run unit tests
            results = await self.unit_test_tool.run_tests(config)
            
            # Cache results
            self._test_results_cache[f"{task.id}_unit"] = results
            
            # Analyze failures if any
            if results.failed > 0:
                await self._analyze_and_remediate_failures(results, project_path)
            
            self.logger.info(f"Unit tests completed: {results.passed}/{results.total_tests} passed")
            
            return {
                "test_type": "unit",
                "results": results.dict(),
                "success": results.is_successful,
                "coverage": results.coverage
            }
            
        except Exception as e:
            self.logger.error(f"Unit test execution failed: {str(e)}")
            raise
    
    async def _run_integration_tests(self, project_state_data: Dict[str, Any], task: Task) -> Dict[str, Any]:
        """Run integration tests for the project."""
        if not self.integration_test_tool:
            raise ValueError("Integration test tool not configured")
        
        self.logger.info("Running integration tests")
        
        # Extract project path from state
        project_path = project_state_data.get("metadata", {}).get("project_path", ".")
        
        # Configure integration tests
        config = TestConfig(
            project_path=project_path,
            test_type=TestType.INTEGRATION,
            test_patterns=["**/*.integration.js", "**/*.integration.ts", "**/e2e/**/*.js", "**/e2e/**/*.ts"],
            timeout=600,
            parallel=False,  # Integration tests often need to run sequentially
            coverage=False
        )
        
        try:
            # Set up test environment
            env_config = {
                "database_url": "sqlite:///:memory:",
                "api_port": 3001,
                "test_mode": True
            }
            environment = await self.integration_test_tool.setup_test_environment(env_config)
            
            # Run integration tests
            results = await self.integration_test_tool.run_integration_tests(config)
            
            # Cache results
            self._test_results_cache[f"{task.id}_integration"] = results
            
            # Analyze failures if any
            if results.failed > 0:
                await self._analyze_and_remediate_failures(results, project_path)
            
            # Cleanup test environment
            await self.integration_test_tool.teardown_test_environment(environment.get("id", ""))
            
            self.logger.info(f"Integration tests completed: {results.passed}/{results.total_tests} passed")
            
            return {
                "test_type": "integration",
                "results": results.dict(),
                "success": results.is_successful,
                "environment": environment
            }
            
        except Exception as e:
            self.logger.error(f"Integration test execution failed: {str(e)}")
            raise
    
    async def _run_ui_tests(self, project_state_data: Dict[str, Any], task: Task) -> Dict[str, Any]:
        """Run UI tests against the deployed application."""
        if not self.ui_test_tool:
            raise ValueError("UI test tool not configured")
        
        self.logger.info("Running UI tests")
        
        # Get deployment URL from project state
        deployment_info = project_state_data.get("deployment_info")
        if not deployment_info:
            raise ValueError("No deployment information found for UI testing")
        
        deployment_url = deployment_info.get("url")
        if not deployment_url:
            raise ValueError("Deployment URL not found")
        
        # Extract project path from state
        project_path = project_state_data.get("metadata", {}).get("project_path", ".")
        
        # Configure UI tests
        config = TestConfig(
            project_path=project_path,
            test_type=TestType.UI,
            test_patterns=["**/ui/**/*.js", "**/ui/**/*.ts", "**/*.ui.js", "**/*.ui.ts"],
            timeout=900,
            parallel=True,
            browser="chromium",
            headless=True,
            viewport={"width": 1280, "height": 720}
        )
        
        try:
            # Run UI tests
            results = await self.ui_test_tool.run_ui_tests(config, deployment_url)
            
            # Cache results
            self._test_results_cache[f"{task.id}_ui"] = results
            
            # Run accessibility tests
            accessibility_violations = await self.ui_test_tool.run_accessibility_tests(deployment_url)
            results.accessibility_violations = accessibility_violations
            
            # Analyze failures if any
            if results.failed > 0:
                await self._analyze_and_remediate_failures(results, project_path)
            
            self.logger.info(f"UI tests completed: {results.passed}/{results.total_tests} passed")
            
            return {
                "test_type": "ui",
                "results": results.dict(),
                "success": results.is_successful,
                "accessibility_violations": len(accessibility_violations),
                "screenshots": results.screenshots
            }
            
        except Exception as e:
            self.logger.error(f"UI test execution failed: {str(e)}")
            raise
    
    async def _analyze_and_remediate_failures(self, results: TestResults, project_path: str) -> None:
        """Analyze test failures and attempt automatic remediation."""
        if not self.failure_analyzer or not results.failures:
            return
        
        self.logger.info(f"Analyzing {len(results.failures)} test failures")
        
        remediation_results = []
        
        for failure in results.failures:
            try:
                # Analyze the failure
                analysis = await self.failure_analyzer.analyze_failure(failure, {
                    "project_path": project_path,
                    "test_type": results.test_type.value
                })
                
                # Categorize the failure
                category = await self.failure_analyzer.categorize_failure(failure)
                failure.category = category
                
                # Suggest a fix
                suggested_fix = await self.failure_analyzer.suggest_fix(failure, category)
                
                if suggested_fix:
                    self.logger.info(f"Attempting automatic fix for {failure.test_name}")
                    
                    # Apply the fix
                    fix_applied = await self.failure_analyzer.apply_fix(
                        failure, suggested_fix, project_path
                    )
                    
                    remediation_results.append({
                        "test_name": failure.test_name,
                        "category": category,
                        "fix_suggested": suggested_fix,
                        "fix_applied": fix_applied,
                        "analysis": analysis
                    })
                
            except Exception as e:
                self.logger.error(f"Failed to analyze failure for {failure.test_name}: {str(e)}")
        
        if remediation_results:
            # Publish remediation event
            await self.publish_event(EventType.ERROR_DETECTED, {
                "project_id": project_path,
                "test_failures_analyzed": len(remediation_results),
                "automatic_fixes_applied": sum(1 for r in remediation_results if r["fix_applied"]),
                "remediation_results": remediation_results
            })
    
    async def _handle_deployment_ready(self, event) -> None:
        """Handle deployment ready events to trigger UI testing."""
        self.logger.info("Deployment ready - scheduling UI tests")
        
        project_id = event.payload.get("project_id")
        if not project_id:
            return
        
        # Create UI testing task
        ui_test_task = Task(
            id=f"{project_id}_ui_test_{datetime.now().isoformat()}",
            type=TaskType.TESTING,
            description="Run UI tests against deployed application",
            dependencies=[],
            estimated_duration=900,  # 15 minutes
            status="pending",
            agent_assigned=self.agent_id,
            metadata={"test_type": "ui", "triggered_by": "deployment_ready"}
        )
        
        # Execute UI tests
        try:
            result = await self.execute_task(ui_test_task)
            
            # Publish test completion event
            await self.publish_event(EventType.TESTS_COMPLETED, {
                "project_id": project_id,
                "test_type": "ui",
                "success": result.get("success", False),
                "results": result
            })
            
        except Exception as e:
            self.logger.error(f"UI test execution failed: {str(e)}")
            await self.publish_event(EventType.ERROR_DETECTED, {
                "project_id": project_id,
                "error": str(e),
                "context": "ui_testing"
            })
    
    async def _handle_task_completed(self, event) -> None:
        """Handle task completion events to trigger appropriate tests."""
        task_type = event.payload.get("task_type")
        project_id = event.payload.get("project_id")
        
        if not project_id:
            return
        
        # Trigger unit tests after code generation
        if task_type == "code_generation":
            self.logger.info("Code generation completed - scheduling unit tests")
            
            unit_test_task = Task(
                id=f"{project_id}_unit_test_{datetime.now().isoformat()}",
                type=TaskType.TESTING,
                description="Run unit tests for generated code",
                dependencies=[],
                estimated_duration=300,  # 5 minutes
                status="pending",
                agent_assigned=self.agent_id,
                metadata={"test_type": "unit", "triggered_by": "code_generation"}
            )
            
            try:
                result = await self.execute_task(unit_test_task)
                
                # Publish test completion event
                await self.publish_event(EventType.TESTS_COMPLETED, {
                    "project_id": project_id,
                    "test_type": "unit",
                    "success": result.get("success", False),
                    "results": result
                })
                
            except Exception as e:
                self.logger.error(f"Unit test execution failed: {str(e)}")
    
    async def get_test_results(self, project_id: str, test_type: Optional[str] = None) -> Dict[str, TestResults]:
        """Get cached test results for a project."""
        if test_type:
            key = f"{project_id}_{test_type}"
            return {key: self._test_results_cache[key]} if key in self._test_results_cache else {}
        
        # Return all test results for the project
        return {
            key: results for key, results in self._test_results_cache.items()
            if key.startswith(project_id)
        }
    
    async def generate_test_report(self, project_id: str) -> Dict[str, Any]:
        """Generate a comprehensive test report for a project."""
        test_results = await self.get_test_results(project_id)
        
        if not test_results:
            return {"error": "No test results found for project"}
        
        total_tests = sum(results.total_tests for results in test_results.values())
        total_passed = sum(results.passed for results in test_results.values())
        total_failed = sum(results.failed for results in test_results.values())
        total_duration = sum(results.duration for results in test_results.values())
        
        # Calculate average coverage
        coverage_results = [r.coverage for r in test_results.values() if r.coverage is not None]
        avg_coverage = sum(coverage_results) / len(coverage_results) if coverage_results else None
        
        return {
            "project_id": project_id,
            "summary": {
                "total_tests": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "success_rate": (total_passed / total_tests * 100) if total_tests > 0 else 0,
                "total_duration": total_duration,
                "average_coverage": avg_coverage
            },
            "test_suites": {
                key: results.dict() for key, results in test_results.items()
            },
            "generated_at": datetime.utcnow().isoformat()
        }