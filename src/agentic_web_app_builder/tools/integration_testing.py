"""Integration testing tool implementation using Cypress/Playwright."""

import asyncio
import json
import os
import subprocess
import tempfile
from typing import Dict, Any, List
from datetime import datetime

from .testing_interfaces import IntegrationTestTool, TestConfig, TestResults, TestFailure, TestType


class CypressPlaywrightTool(IntegrationTestTool):
    """Integration testing tool using Cypress or Playwright."""
    
    def __init__(self):
        self.logger = None
        self._test_environments: Dict[str, Dict[str, Any]] = {}
    
    async def run_integration_tests(self, config: TestConfig) -> TestResults:
        """Run integration tests using Cypress or Playwright."""
        # Detect which integration test runner to use
        test_runner = await self._detect_integration_runner(config.project_path)
        
        if test_runner == "playwright":
            return await self._run_playwright(config)
        elif test_runner == "cypress":
            return await self._run_cypress(config)
        else:
            # Fallback to generic integration testing
            return await self._run_generic_integration(config)
    
    async def _detect_integration_runner(self, project_path: str) -> str:
        """Detect which integration test runner is configured."""
        package_json_path = os.path.join(project_path, "package.json")
        
        if not os.path.exists(package_json_path):
            return "generic"
        
        try:
            with open(package_json_path, 'r') as f:
                package_data = json.load(f)
            
            dependencies = {
                **package_data.get("dependencies", {}),
                **package_data.get("devDependencies", {})
            }
            
            if "@playwright/test" in dependencies or "playwright" in dependencies:
                return "playwright"
            elif "cypress" in dependencies:
                return "cypress"
            else:
                return "generic"
                
        except Exception:
            return "generic"
    
    async def _run_playwright(self, config: TestConfig) -> TestResults:
        """Run integration tests using Playwright."""
        cmd = ["npx", "playwright", "test"]
        
        # Add configuration options
        if config.parallel:
            cmd.extend(["--workers", "4"])
        else:
            cmd.extend(["--workers", "1"])
        
        # Add reporter for JSON output
        cmd.extend(["--reporter=json"])
        
        # Set environment variables
        env = os.environ.copy()
        env.update(config.environment)
        env["CI"] = "true"
        
        try:
            # Run playwright
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=config.project_path,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=config.timeout
            )
            
            # Parse playwright output
            return await self._parse_playwright_output(stdout.decode(), stderr.decode(), config)
            
        except asyncio.TimeoutError:
            raise Exception(f"Integration test execution timed out after {config.timeout} seconds")
        except Exception as e:
            raise Exception(f"Failed to run Playwright: {str(e)}")
    
    async def _run_cypress(self, config: TestConfig) -> TestResults:
        """Run integration tests using Cypress."""
        cmd = ["npx", "cypress", "run"]
        
        # Add configuration options
        cmd.extend(["--reporter", "json"])
        
        if config.browser:
            cmd.extend(["--browser", config.browser])
        
        if config.headless:
            cmd.append("--headless")
        
        # Set environment variables
        env = os.environ.copy()
        env.update(config.environment)
        env["CI"] = "true"
        
        try:
            # Run cypress
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=config.project_path,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=config.timeout
            )
            
            # Parse cypress output
            return await self._parse_cypress_output(stdout.decode(), stderr.decode(), config)
            
        except asyncio.TimeoutError:
            raise Exception(f"Integration test execution timed out after {config.timeout} seconds")
        except Exception as e:
            raise Exception(f"Failed to run Cypress: {str(e)}")
    
    async def _run_generic_integration(self, config: TestConfig) -> TestResults:
        """Run generic integration tests."""
        # Look for integration test files and run them with available test runner
        test_files = await self._find_integration_test_files(config.project_path, config.test_patterns)
        
        if not test_files:
            return TestResults(
                test_suite="generic-integration",
                test_type=TestType.INTEGRATION,
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                duration=0.0,
                failures=[]
            )
        
        # Try to run with available test runner
        cmd = ["npm", "run", "test:integration"]
        
        env = os.environ.copy()
        env.update(config.environment)
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=config.project_path,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=config.timeout
            )
            
            return await self._parse_generic_output(stdout.decode(), stderr.decode(), config)
            
        except Exception as e:
            # If npm script doesn't exist, create a basic test result
            return TestResults(
                test_suite="generic-integration",
                test_type=TestType.INTEGRATION,
                total_tests=len(test_files),
                passed=0,
                failed=len(test_files),
                skipped=0,
                duration=0.0,
                failures=[
                    TestFailure(
                        test_name=f"Integration test setup",
                        error_message=f"Failed to run integration tests: {str(e)}",
                        stack_trace=None
                    )
                ]
            )
    
    async def _find_integration_test_files(self, project_path: str, patterns: List[str]) -> List[str]:
        """Find integration test files matching the given patterns."""
        import glob
        
        test_files = []
        for pattern in patterns:
            full_pattern = os.path.join(project_path, pattern)
            test_files.extend(glob.glob(full_pattern, recursive=True))
        
        return test_files
    
    async def _parse_playwright_output(self, stdout: str, stderr: str, config: TestConfig) -> TestResults:
        """Parse Playwright JSON output."""
        failures = []
        
        try:
            # Try to parse JSON output
            if stdout.strip():
                playwright_results = json.loads(stdout)
                
                # Extract test results
                total_tests = len(playwright_results.get("tests", []))
                passed = 0
                failed = 0
                skipped = 0
                duration = 0.0
                
                for test in playwright_results.get("tests", []):
                    status = test.get("status", "unknown")
                    if status == "passed":
                        passed += 1
                    elif status == "failed":
                        failed += 1
                        # Extract failure information
                        failure = TestFailure(
                            test_name=test.get("title", "Unknown test"),
                            error_message=test.get("error", {}).get("message", "Test failed"),
                            stack_trace=test.get("error", {}).get("stack"),
                            file_path=test.get("location", {}).get("file")
                        )
                        failures.append(failure)
                    elif status == "skipped":
                        skipped += 1
                
                # Calculate total duration
                duration = sum(test.get("duration", 0) for test in playwright_results.get("tests", [])) / 1000
                
                return TestResults(
                    test_suite="playwright",
                    test_type=config.test_type,
                    total_tests=total_tests,
                    passed=passed,
                    failed=failed,
                    skipped=skipped,
                    duration=duration,
                    failures=failures
                )
        
        except json.JSONDecodeError:
            pass
        
        # Fallback to parsing text output
        return await self._parse_generic_output(stdout, stderr, config)
    
    async def _parse_cypress_output(self, stdout: str, stderr: str, config: TestConfig) -> TestResults:
        """Parse Cypress JSON output."""
        failures = []
        
        try:
            # Cypress outputs JSON to stdout
            if stdout.strip():
                cypress_results = json.loads(stdout)
                
                total_tests = cypress_results.get("totalTests", 0)
                passed = cypress_results.get("totalPassed", 0)
                failed = cypress_results.get("totalFailed", 0)
                skipped = cypress_results.get("totalSkipped", 0)
                duration = cypress_results.get("totalDuration", 0) / 1000
                
                # Extract failures
                for run in cypress_results.get("runs", []):
                    for test in run.get("tests", []):
                        if test.get("state") == "failed":
                            failure = TestFailure(
                                test_name=test.get("title", ["Unknown test"])[-1],
                                error_message=test.get("err", {}).get("message", "Test failed"),
                                stack_trace=test.get("err", {}).get("stack"),
                                file_path=run.get("spec", {}).get("relative")
                            )
                            failures.append(failure)
                
                return TestResults(
                    test_suite="cypress",
                    test_type=config.test_type,
                    total_tests=total_tests,
                    passed=passed,
                    failed=failed,
                    skipped=skipped,
                    duration=duration,
                    failures=failures
                )
        
        except json.JSONDecodeError:
            pass
        
        # Fallback to parsing text output
        return await self._parse_generic_output(stdout, stderr, config)
    
    async def _parse_generic_output(self, stdout: str, stderr: str, config: TestConfig) -> TestResults:
        """Parse generic integration test output."""
        failures = []
        
        # Basic parsing for generic output
        total_tests = 0
        passed = 0
        failed = 0
        duration = 0.0
        
        lines = stdout.split('\n') + stderr.split('\n')
        
        for line in lines:
            line_lower = line.lower()
            
            if "test" in line_lower and ("pass" in line_lower or "✓" in line):
                import re
                numbers = re.findall(r'\d+', line)
                if numbers:
                    passed = max(passed, int(numbers[0]))
            
            elif "test" in line_lower and ("fail" in line_lower or "✗" in line):
                import re
                numbers = re.findall(r'\d+', line)
                if numbers:
                    failed = max(failed, int(numbers[0]))
            
            elif "error" in line_lower or "fail" in line_lower:
                failure = TestFailure(
                    test_name="Integration test failure",
                    error_message=line.strip(),
                    stack_trace=None
                )
                failures.append(failure)
        
        total_tests = max(total_tests, passed + failed)
        
        return TestResults(
            test_suite="generic-integration",
            test_type=config.test_type,
            total_tests=total_tests,
            passed=passed,
            failed=failed,
            skipped=0,
            duration=duration,
            failures=failures
        )
    
    async def setup_test_environment(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Set up test environment for integration tests."""
        environment_id = f"test_env_{datetime.now().isoformat()}"
        
        # Create temporary directory for test data
        temp_dir = tempfile.mkdtemp(prefix="integration_test_")
        
        # Set up test database if specified
        database_url = config.get("database_url")
        if database_url and database_url.startswith("sqlite://"):
            # Create test database
            db_path = os.path.join(temp_dir, "test.db")
            config["database_url"] = f"sqlite:///{db_path}"
        
        # Set up test server if specified
        api_port = config.get("api_port", 3001)
        test_server_process = None
        
        if config.get("start_test_server", False):
            # Start test server (this would be project-specific)
            try:
                test_server_process = await asyncio.create_subprocess_exec(
                    "npm", "run", "start:test",
                    env={**os.environ, "PORT": str(api_port), "NODE_ENV": "test"},
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                # Wait a bit for server to start
                await asyncio.sleep(2)
                
            except Exception as e:
                # Server startup failed, continue without it
                test_server_process = None
        
        environment = {
            "id": environment_id,
            "temp_dir": temp_dir,
            "database_url": config.get("database_url"),
            "api_port": api_port,
            "test_server_process": test_server_process,
            "config": config,
            "created_at": datetime.now().isoformat()
        }
        
        self._test_environments[environment_id] = environment
        
        return environment
    
    async def teardown_test_environment(self, environment_id: str) -> bool:
        """Tear down test environment."""
        if environment_id not in self._test_environments:
            return False
        
        environment = self._test_environments[environment_id]
        
        try:
            # Stop test server if running
            test_server_process = environment.get("test_server_process")
            if test_server_process:
                test_server_process.terminate()
                await test_server_process.wait()
            
            # Clean up temporary directory
            temp_dir = environment.get("temp_dir")
            if temp_dir and os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)
            
            # Remove from tracking
            del self._test_environments[environment_id]
            
            return True
            
        except Exception as e:
            # Log error but don't fail
            return False
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """Validate integration testing parameters."""
        config = parameters.get("config", {})
        required_fields = ["project_path", "test_type"]
        return all(field in config for field in required_fields)