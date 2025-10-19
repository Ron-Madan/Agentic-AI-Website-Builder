"""Unit testing tool implementation using Jest/Vitest."""

import asyncio
import json
import os
import subprocess
from typing import Dict, Any, List
from datetime import datetime

from .testing_interfaces import UnitTestTool, TestConfig, TestResults, TestFailure, TestType


class JestVitestTool(UnitTestTool):
    """Unit testing tool using Jest or Vitest based on project configuration."""
    
    def __init__(self):
        self.logger = None
    
    async def run_tests(self, config: TestConfig) -> TestResults:
        """Run unit tests using Jest or Vitest."""
        # Determine which test runner to use
        test_runner = await self._detect_test_runner(config.project_path)
        
        if test_runner == "vitest":
            return await self._run_vitest(config)
        elif test_runner == "jest":
            return await self._run_jest(config)
        else:
            # Fallback to npm test
            return await self._run_npm_test(config)
    
    async def _detect_test_runner(self, project_path: str) -> str:
        """Detect which test runner is configured in the project."""
        package_json_path = os.path.join(project_path, "package.json")
        
        if not os.path.exists(package_json_path):
            return "npm"
        
        try:
            with open(package_json_path, 'r') as f:
                package_data = json.load(f)
            
            # Check dependencies
            dependencies = {
                **package_data.get("dependencies", {}),
                **package_data.get("devDependencies", {})
            }
            
            if "vitest" in dependencies:
                return "vitest"
            elif "jest" in dependencies:
                return "jest"
            else:
                return "npm"
                
        except Exception:
            return "npm"
    
    async def _run_vitest(self, config: TestConfig) -> TestResults:
        """Run tests using Vitest."""
        cmd = ["npx", "vitest", "run"]
        
        # Add configuration options
        if config.coverage:
            cmd.extend(["--coverage"])
        
        if config.test_patterns:
            # Vitest uses different pattern syntax
            for pattern in config.test_patterns:
                cmd.extend(["--include", pattern])
        
        # Set environment variables
        env = os.environ.copy()
        env.update(config.environment)
        env["CI"] = "true"  # Ensure non-interactive mode
        
        try:
            # Run vitest
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
            
            # Parse vitest output
            return await self._parse_vitest_output(stdout.decode(), stderr.decode(), config)
            
        except asyncio.TimeoutError:
            raise Exception(f"Test execution timed out after {config.timeout} seconds")
        except Exception as e:
            raise Exception(f"Failed to run vitest: {str(e)}")
    
    async def _run_jest(self, config: TestConfig) -> TestResults:
        """Run tests using Jest."""
        cmd = ["npx", "jest"]
        
        # Add configuration options
        if config.coverage:
            cmd.append("--coverage")
        
        if config.parallel:
            cmd.append("--runInBand")  # Jest runs in parallel by default
        
        # Add JSON reporter for easier parsing
        cmd.extend(["--json", "--outputFile=test-results.json"])
        
        # Set environment variables
        env = os.environ.copy()
        env.update(config.environment)
        env["CI"] = "true"
        
        try:
            # Run jest
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
            
            # Parse jest output
            return await self._parse_jest_output(config.project_path, stdout.decode(), stderr.decode())
            
        except asyncio.TimeoutError:
            raise Exception(f"Test execution timed out after {config.timeout} seconds")
        except Exception as e:
            raise Exception(f"Failed to run jest: {str(e)}")
    
    async def _run_npm_test(self, config: TestConfig) -> TestResults:
        """Run tests using npm test command."""
        cmd = ["npm", "test"]
        
        # Set environment variables
        env = os.environ.copy()
        env.update(config.environment)
        env["CI"] = "true"
        
        try:
            # Run npm test
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
            
            # Parse generic test output
            return await self._parse_generic_output(stdout.decode(), stderr.decode(), config)
            
        except asyncio.TimeoutError:
            raise Exception(f"Test execution timed out after {config.timeout} seconds")
        except Exception as e:
            raise Exception(f"Failed to run npm test: {str(e)}")
    
    async def _parse_vitest_output(self, stdout: str, stderr: str, config: TestConfig) -> TestResults:
        """Parse Vitest output to extract test results."""
        failures = []
        
        # Basic parsing - in a real implementation, you'd parse the actual Vitest output format
        lines = stdout.split('\n')
        
        total_tests = 0
        passed = 0
        failed = 0
        duration = 0.0
        coverage = None
        
        for line in lines:
            if "Test Files" in line:
                # Extract test counts from summary
                parts = line.split()
                for i, part in enumerate(parts):
                    if part.isdigit():
                        if "passed" in line:
                            passed = int(part)
                        elif "failed" in line:
                            failed = int(part)
            
            elif "Time:" in line:
                # Extract duration
                try:
                    time_part = line.split("Time:")[1].strip()
                    if "ms" in time_part:
                        duration = float(time_part.replace("ms", "")) / 1000
                    elif "s" in time_part:
                        duration = float(time_part.replace("s", ""))
                except:
                    pass
            
            elif "Coverage:" in line:
                # Extract coverage percentage
                try:
                    coverage_part = line.split("Coverage:")[1].strip()
                    coverage = float(coverage_part.replace("%", ""))
                except:
                    pass
            
            elif "FAIL" in line:
                # Parse failure information
                failure = TestFailure(
                    test_name=line.split("FAIL")[1].strip(),
                    error_message="Test failed",
                    stack_trace=None
                )
                failures.append(failure)
        
        total_tests = passed + failed
        
        return TestResults(
            test_suite="vitest",
            test_type=config.test_type,
            total_tests=total_tests,
            passed=passed,
            failed=failed,
            skipped=0,
            duration=duration,
            coverage=coverage,
            failures=failures
        )
    
    async def _parse_jest_output(self, project_path: str, stdout: str, stderr: str) -> TestResults:
        """Parse Jest JSON output to extract test results."""
        json_file_path = os.path.join(project_path, "test-results.json")
        
        try:
            if os.path.exists(json_file_path):
                with open(json_file_path, 'r') as f:
                    jest_results = json.load(f)
                
                # Clean up the JSON file
                os.remove(json_file_path)
                
                # Extract test results from Jest JSON
                total_tests = jest_results.get("numTotalTests", 0)
                passed = jest_results.get("numPassedTests", 0)
                failed = jest_results.get("numFailedTests", 0)
                skipped = jest_results.get("numPendingTests", 0)
                duration = jest_results.get("testResults", [{}])[0].get("perfStats", {}).get("runtime", 0) / 1000
                
                # Extract coverage if available
                coverage = None
                if "coverageMap" in jest_results:
                    coverage_data = jest_results["coverageMap"]
                    if coverage_data:
                        # Calculate average coverage
                        total_coverage = 0
                        file_count = 0
                        for file_data in coverage_data.values():
                            if "pct" in file_data.get("statements", {}):
                                total_coverage += file_data["statements"]["pct"]
                                file_count += 1
                        coverage = total_coverage / file_count if file_count > 0 else None
                
                # Extract failures
                failures = []
                for test_result in jest_results.get("testResults", []):
                    for assertion in test_result.get("assertionResults", []):
                        if assertion.get("status") == "failed":
                            failure = TestFailure(
                                test_name=assertion.get("title", "Unknown test"),
                                error_message=assertion.get("failureMessages", ["Unknown error"])[0],
                                stack_trace=assertion.get("failureMessages", [""])[0],
                                file_path=test_result.get("name")
                            )
                            failures.append(failure)
                
                return TestResults(
                    test_suite="jest",
                    test_type=TestType.UNIT,
                    total_tests=total_tests,
                    passed=passed,
                    failed=failed,
                    skipped=skipped,
                    duration=duration,
                    coverage=coverage,
                    failures=failures
                )
            
            else:
                # Fallback to parsing stdout
                return await self._parse_generic_output(stdout, stderr, TestConfig(
                    project_path=project_path,
                    test_type=TestType.UNIT
                ))
                
        except Exception as e:
            raise Exception(f"Failed to parse Jest output: {str(e)}")
    
    async def _parse_generic_output(self, stdout: str, stderr: str, config: TestConfig) -> TestResults:
        """Parse generic test output when specific parsers aren't available."""
        # Basic parsing for generic test output
        failures = []
        
        # Look for common test result patterns
        total_tests = 0
        passed = 0
        failed = 0
        duration = 0.0
        
        lines = stdout.split('\n') + stderr.split('\n')
        
        for line in lines:
            line = line.lower()
            
            if "test" in line and "pass" in line:
                # Try to extract numbers
                import re
                numbers = re.findall(r'\d+', line)
                if numbers:
                    passed = int(numbers[0])
            
            elif "fail" in line and "test" in line:
                import re
                numbers = re.findall(r'\d+', line)
                if numbers:
                    failed = int(numbers[0])
            
            elif "error" in line or "fail" in line:
                failure = TestFailure(
                    test_name="Generic test failure",
                    error_message=line.strip(),
                    stack_trace=None
                )
                failures.append(failure)
        
        total_tests = passed + failed
        
        return TestResults(
            test_suite="generic",
            test_type=config.test_type,
            total_tests=total_tests,
            passed=passed,
            failed=failed,
            skipped=0,
            duration=duration,
            coverage=None,
            failures=failures
        )
    
    async def generate_test_files(self, source_files: List[str]) -> Dict[str, str]:
        """Generate test files for given source files."""
        generated_tests = {}
        
        for source_file in source_files:
            # Determine test file name
            if source_file.endswith('.ts'):
                test_file = source_file.replace('.ts', '.test.ts')
            elif source_file.endswith('.js'):
                test_file = source_file.replace('.js', '.test.js')
            else:
                continue
            
            # Generate basic test template
            test_content = await self._generate_test_template(source_file)
            generated_tests[test_file] = test_content
        
        return generated_tests
    
    async def _generate_test_template(self, source_file: str) -> str:
        """Generate a basic test template for a source file."""
        file_name = os.path.basename(source_file)
        module_name = file_name.split('.')[0]
        
        # Basic test template
        template = f'''import {{ describe, it, expect }} from 'vitest';
import {{ {module_name} }} from './{module_name}';

describe('{module_name}', () => {{
  it('should be defined', () => {{
    expect({module_name}).toBeDefined();
  }});

  // Add more specific tests here
  it('should work correctly', () => {{
    // TODO: Implement test logic
    expect(true).toBe(true);
  }});
}});
'''
        
        return template
    
    async def analyze_coverage(self, project_path: str) -> Dict[str, Any]:
        """Analyze test coverage for the project."""
        # Run coverage analysis
        cmd = ["npx", "vitest", "run", "--coverage", "--reporter=json"]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Parse coverage output
            coverage_data = {
                "overall_coverage": 0.0,
                "file_coverage": {},
                "uncovered_lines": [],
                "coverage_report_path": os.path.join(project_path, "coverage")
            }
            
            # In a real implementation, you'd parse the actual coverage JSON
            return coverage_data
            
        except Exception as e:
            return {
                "error": f"Failed to analyze coverage: {str(e)}",
                "overall_coverage": 0.0,
                "file_coverage": {},
                "uncovered_lines": []
            }
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """Validate unit testing parameters."""
        config = parameters.get("config", {})
        required_fields = ["project_path", "test_type"]
        return all(field in config for field in required_fields)