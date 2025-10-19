"""UI testing tool implementation using Playwright for headless browser testing."""

import asyncio
import json
import os
import tempfile
from typing import Dict, Any, List
from datetime import datetime

from .testing_interfaces import UITestTool, TestConfig, UITestResults, TestFailure, TestType


class PlaywrightUITool(UITestTool):
    """UI testing tool using Playwright for headless browser automation."""
    
    def __init__(self):
        self.logger = None
        self._screenshot_dir = None
        self._baseline_dir = None
    
    async def run_ui_tests(self, config: TestConfig, deployment_url: str) -> UITestResults:
        """Run UI tests against a deployed application."""
        # Set up screenshot directory
        self._screenshot_dir = os.path.join(config.project_path, "test-screenshots")
        os.makedirs(self._screenshot_dir, exist_ok=True)
        
        # Create Playwright test configuration
        playwright_config = await self._create_playwright_config(config, deployment_url)
        
        # Run Playwright tests
        cmd = ["npx", "playwright", "test"]
        
        # Add configuration options
        if config.parallel:
            cmd.extend(["--workers", "4"])
        else:
            cmd.extend(["--workers", "1"])
        
        # Add reporter for JSON output
        cmd.extend(["--reporter=json"])
        
        # Set browser
        if config.browser:
            cmd.extend(["--project", config.browser])
        
        # Set environment variables
        env = os.environ.copy()
        env.update(config.environment)
        env["CI"] = "true"
        env["BASE_URL"] = deployment_url
        
        try:
            # Run playwright UI tests
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
            results = await self._parse_playwright_ui_output(stdout.decode(), stderr.decode(), config)
            
            # Collect screenshots
            results.screenshots = await self._collect_screenshots()
            
            return results
            
        except asyncio.TimeoutError:
            raise Exception(f"UI test execution timed out after {config.timeout} seconds")
        except Exception as e:
            raise Exception(f"Failed to run Playwright UI tests: {str(e)}")
    
    async def _create_playwright_config(self, config: TestConfig, deployment_url: str) -> str:
        """Create Playwright configuration file for UI testing."""
        playwright_config = {
            "testDir": "./tests/ui",
            "fullyParallel": config.parallel,
            "forbidOnly": True,
            "retries": 2,
            "workers": 4 if config.parallel else 1,
            "reporter": [["json", {"outputFile": "test-results.json"}]],
            "use": {
                "baseURL": deployment_url,
                "trace": "on-first-retry",
                "screenshot": "only-on-failure",
                "video": "retain-on-failure"
            },
            "projects": [
                {
                    "name": "chromium",
                    "use": {"...devices['Desktop Chrome']"}
                },
                {
                    "name": "firefox",
                    "use": {"...devices['Desktop Firefox']"}
                },
                {
                    "name": "webkit",
                    "use": {"...devices['Desktop Safari']"}
                }
            ]
        }
        
        # Add viewport configuration
        if config.viewport:
            playwright_config["use"]["viewport"] = config.viewport
        
        # Write configuration file
        config_path = os.path.join(config.project_path, "playwright.config.js")
        config_content = f"""
const {{ defineConfig, devices }} = require('@playwright/test');

module.exports = defineConfig({json.dumps(playwright_config, indent=2)});
"""
        
        with open(config_path, 'w') as f:
            f.write(config_content)
        
        return config_path
    
    async def _parse_playwright_ui_output(self, stdout: str, stderr: str, config: TestConfig) -> UITestResults:
        """Parse Playwright UI test output."""
        failures = []
        screenshots = []
        performance_metrics = {}
        
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
                            test_name=test.get("title", "Unknown UI test"),
                            error_message=test.get("error", {}).get("message", "UI test failed"),
                            stack_trace=test.get("error", {}).get("stack"),
                            file_path=test.get("location", {}).get("file")
                        )
                        failures.append(failure)
                    elif status == "skipped":
                        skipped += 1
                    
                    # Extract performance metrics if available
                    if "performance" in test:
                        performance_metrics[test.get("title", "unknown")] = test["performance"]
                
                # Calculate total duration
                duration = sum(test.get("duration", 0) for test in playwright_results.get("tests", [])) / 1000
                
                return UITestResults(
                    test_suite="playwright-ui",
                    test_type=TestType.UI,
                    total_tests=total_tests,
                    passed=passed,
                    failed=failed,
                    skipped=skipped,
                    duration=duration,
                    failures=failures,
                    screenshots=screenshots,
                    performance_metrics=performance_metrics
                )
        
        except json.JSONDecodeError:
            pass
        
        # Fallback to parsing text output
        return await self._parse_generic_ui_output(stdout, stderr, config)
    
    async def _parse_generic_ui_output(self, stdout: str, stderr: str, config: TestConfig) -> UITestResults:
        """Parse generic UI test output."""
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
                    test_name="UI test failure",
                    error_message=line.strip(),
                    stack_trace=None
                )
                failures.append(failure)
        
        total_tests = max(total_tests, passed + failed)
        
        return UITestResults(
            test_suite="generic-ui",
            test_type=TestType.UI,
            total_tests=total_tests,
            passed=passed,
            failed=failed,
            skipped=0,
            duration=duration,
            failures=failures,
            screenshots=[],
            performance_metrics={}
        )
    
    async def capture_screenshots(self, url: str, selectors: List[str]) -> List[str]:
        """Capture screenshots of specific elements."""
        screenshots = []
        
        # Create temporary Playwright script
        script_content = f"""
const {{ chromium }} = require('playwright');

(async () => {{
    const browser = await chromium.launch({{ headless: true }});
    const page = await browser.newPage();
    
    try {{
        await page.goto('{url}');
        await page.waitForLoadState('networkidle');
        
        // Capture full page screenshot
        const fullPagePath = 'screenshot_full_page.png';
        await page.screenshot({{ path: fullPagePath, fullPage: true }});
        console.log('Full page screenshot:', fullPagePath);
        
        // Capture element screenshots
        {self._generate_selector_screenshots(selectors)}
        
    }} catch (error) {{
        console.error('Screenshot capture failed:', error);
    }} finally {{
        await browser.close();
    }})();
"""
        
        # Write script to temporary file
        script_path = os.path.join(self._screenshot_dir, "capture_screenshots.js")
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        try:
            # Run the screenshot script
            process = await asyncio.create_subprocess_exec(
                "node", script_path,
                cwd=self._screenshot_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Collect generated screenshots
            for line in stdout.decode().split('\n'):
                if 'screenshot:' in line:
                    screenshot_path = line.split('screenshot:')[1].strip()
                    full_path = os.path.join(self._screenshot_dir, screenshot_path)
                    if os.path.exists(full_path):
                        screenshots.append(full_path)
            
            # Clean up script file
            os.remove(script_path)
            
        except Exception as e:
            raise Exception(f"Failed to capture screenshots: {str(e)}")
        
        return screenshots
    
    def _generate_selector_screenshots(self, selectors: List[str]) -> str:
        """Generate JavaScript code for capturing element screenshots."""
        script_parts = []
        
        for i, selector in enumerate(selectors):
            script_parts.append(f"""
        try {{
            const element_{i} = await page.locator('{selector}').first();
            if (await element_{i}.isVisible()) {{
                const elementPath = 'screenshot_element_{i}.png';
                await element_{i}.screenshot({{ path: elementPath }});
                console.log('Element screenshot:', elementPath);
            }}
        }} catch (e) {{
            console.warn('Failed to capture element {selector}:', e.message);
        }}
""")
        
        return '\n'.join(script_parts)
    
    async def run_accessibility_tests(self, url: str) -> List[Dict[str, Any]]:
        """Run accessibility tests on the application."""
        violations = []
        
        # Create accessibility test script using axe-core
        script_content = f"""
const {{ chromium }} = require('playwright');
const AxeBuilder = require('@axe-core/playwright').default;

(async () => {{
    const browser = await chromium.launch({{ headless: true }});
    const page = await browser.newPage();
    
    try {{
        await page.goto('{url}');
        await page.waitForLoadState('networkidle');
        
        const accessibilityScanResults = await new AxeBuilder({{ page }}).analyze();
        
        console.log('ACCESSIBILITY_RESULTS:', JSON.stringify(accessibilityScanResults.violations));
        
    }} catch (error) {{
        console.error('Accessibility test failed:', error);
    }} finally {{
        await browser.close();
    }})();
"""
        
        # Write script to temporary file
        script_path = os.path.join(self._screenshot_dir, "accessibility_test.js")
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        try:
            # Run the accessibility test script
            process = await asyncio.create_subprocess_exec(
                "node", script_path,
                cwd=self._screenshot_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Parse accessibility results
            for line in stdout.decode().split('\n'):
                if 'ACCESSIBILITY_RESULTS:' in line:
                    try:
                        results_json = line.split('ACCESSIBILITY_RESULTS:')[1].strip()
                        violations = json.loads(results_json)
                        break
                    except json.JSONDecodeError:
                        pass
            
            # Clean up script file
            os.remove(script_path)
            
        except Exception as e:
            # Return basic violation if accessibility testing fails
            violations = [{
                "id": "accessibility-test-error",
                "impact": "serious",
                "description": f"Accessibility testing failed: {str(e)}",
                "nodes": []
            }]
        
        return violations
    
    async def run_visual_regression_tests(self, url: str, baseline_dir: str) -> List[str]:
        """Run visual regression tests against baseline images."""
        visual_diffs = []
        
        if not os.path.exists(baseline_dir):
            os.makedirs(baseline_dir, exist_ok=True)
            # First run - create baseline images
            await self._create_baseline_images(url, baseline_dir)
            return []  # No diffs on first run
        
        # Create comparison script
        script_content = f"""
const {{ chromium }} = require('playwright');
const {{ compare }} = require('resemblejs');
const fs = require('fs');
const path = require('path');

(async () => {{
    const browser = await chromium.launch({{ headless: true }});
    const page = await browser.newPage();
    
    try {{
        await page.goto('{url}');
        await page.waitForLoadState('networkidle');
        
        // Capture current screenshot
        const currentPath = 'current_screenshot.png';
        await page.screenshot({{ path: currentPath, fullPage: true }});
        
        // Compare with baseline
        const baselinePath = path.join('{baseline_dir}', 'baseline_screenshot.png');
        
        if (fs.existsSync(baselinePath)) {{
            const comparison = await compare(baselinePath, currentPath);
            
            if (comparison.misMatchPercentage > 0.1) {{ // 0.1% threshold
                const diffPath = 'visual_diff.png';
                fs.writeFileSync(diffPath, comparison.getBuffer());
                console.log('VISUAL_DIFF:', diffPath, comparison.misMatchPercentage);
            }}
        }}
        
    }} catch (error) {{
        console.error('Visual regression test failed:', error);
    }} finally {{
        await browser.close();
    }})();
"""
        
        # Write script to temporary file
        script_path = os.path.join(self._screenshot_dir, "visual_regression.js")
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        try:
            # Run the visual regression script
            process = await asyncio.create_subprocess_exec(
                "node", script_path,
                cwd=self._screenshot_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Parse visual diff results
            for line in stdout.decode().split('\n'):
                if 'VISUAL_DIFF:' in line:
                    parts = line.split('VISUAL_DIFF:')[1].strip().split()
                    if len(parts) >= 2:
                        diff_path = parts[0]
                        mismatch_percentage = parts[1]
                        full_diff_path = os.path.join(self._screenshot_dir, diff_path)
                        if os.path.exists(full_diff_path):
                            visual_diffs.append(f"{full_diff_path} ({mismatch_percentage}% difference)")
            
            # Clean up script file
            os.remove(script_path)
            
        except Exception as e:
            visual_diffs.append(f"Visual regression test failed: {str(e)}")
        
        return visual_diffs
    
    async def _create_baseline_images(self, url: str, baseline_dir: str) -> None:
        """Create baseline images for visual regression testing."""
        script_content = f"""
const {{ chromium }} = require('playwright');
const path = require('path');

(async () => {{
    const browser = await chromium.launch({{ headless: true }});
    const page = await browser.newPage();
    
    try {{
        await page.goto('{url}');
        await page.waitForLoadState('networkidle');
        
        // Capture baseline screenshot
        const baselinePath = path.join('{baseline_dir}', 'baseline_screenshot.png');
        await page.screenshot({{ path: baselinePath, fullPage: true }});
        
        console.log('Baseline image created:', baselinePath);
        
    }} catch (error) {{
        console.error('Baseline creation failed:', error);
    }} finally {{
        await browser.close();
    }})();
"""
        
        # Write script to temporary file
        script_path = os.path.join(self._screenshot_dir, "create_baseline.js")
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        try:
            # Run the baseline creation script
            process = await asyncio.create_subprocess_exec(
                "node", script_path,
                cwd=self._screenshot_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            # Clean up script file
            os.remove(script_path)
            
        except Exception as e:
            raise Exception(f"Failed to create baseline images: {str(e)}")
    
    async def _collect_screenshots(self) -> List[str]:
        """Collect all screenshots from the screenshot directory."""
        screenshots = []
        
        if not self._screenshot_dir or not os.path.exists(self._screenshot_dir):
            return screenshots
        
        for filename in os.listdir(self._screenshot_dir):
            if filename.endswith(('.png', '.jpg', '.jpeg')):
                full_path = os.path.join(self._screenshot_dir, filename)
                screenshots.append(full_path)
        
        return screenshots
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """Validate UI testing parameters."""
        config = parameters.get("config", {})
        deployment_url = parameters.get("deployment_url", "")
        
        required_fields = ["project_path", "test_type"]
        return (
            all(field in config for field in required_fields) and
            deployment_url.startswith(('http://', 'https://'))
        )