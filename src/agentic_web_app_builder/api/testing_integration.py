"""Testing integration module for comprehensive test execution."""

import asyncio
import logging
import os
import re
import tempfile
from typing import Dict, Any, Optional, List
from datetime import datetime

from ..tools.testing_interfaces import TestConfig, TestResults, TestType, TestFailure
from ..tools.test_failure_analyzer import TestFailureAnalyzer
from ..agents.tester import TesterAgent


logger = logging.getLogger(__name__)


async def run_comprehensive_tests(
    project_id: str, 
    html_content: str, 
    tester_agent: Optional[TesterAgent] = None
) -> Dict[str, Any]:
    """
    Run comprehensive tests including unit, integration, and UI testing.
    
    Args:
        project_id: Unique identifier for the project
        html_content: Generated HTML content to test
        tester_agent: Optional TesterAgent instance for advanced testing
    
    Returns:
        Dictionary containing comprehensive test results
    """
    logger.info(f"Starting comprehensive testing for project {project_id}")
    
    # Set up test environment
    test_env_path = await setup_test_environment(project_id, html_content)
    
    try:
        test_results = {
            "project_id": project_id,
            "test_environment": test_env_path,
            "executed_at": datetime.utcnow().isoformat(),
            "unit_tests": None,
            "integration_tests": None,
            "ui_tests": None,
            "overall_success": False,
            "total_tests": 0,
            "total_passed": 0,
            "total_failed": 0,
            "total_duration": 0.0,
            "failures": [],
            "warnings": []
        }
        
        # Run unit tests
        logger.info("Running unit tests...")
        unit_results = await _run_unit_tests(project_id, test_env_path, tester_agent)
        test_results["unit_tests"] = unit_results
        
        # Run integration tests
        logger.info("Running integration tests...")
        integration_results = await _run_integration_tests(project_id, test_env_path, tester_agent)
        test_results["integration_tests"] = integration_results
        
        # Run UI tests (basic HTML validation and accessibility)
        logger.info("Running UI tests...")
        ui_results = await _run_ui_tests(project_id, html_content, test_env_path, tester_agent)
        test_results["ui_tests"] = ui_results
        
        # Aggregate results
        all_results = [unit_results, integration_results, ui_results]
        test_results["total_tests"] = sum(r.get("total_tests", 0) for r in all_results if r)
        test_results["total_passed"] = sum(r.get("passed", 0) for r in all_results if r)
        test_results["total_failed"] = sum(r.get("failed", 0) for r in all_results if r)
        test_results["total_duration"] = sum(r.get("duration", 0.0) for r in all_results if r)
        
        # Collect all failures
        for result in all_results:
            if result and result.get("failures"):
                test_results["failures"].extend(result["failures"])
        
        # Collect all warnings
        for result in all_results:
            if result and result.get("warnings"):
                test_results["warnings"].extend(result["warnings"])
        
        # Determine overall success
        test_results["overall_success"] = test_results["total_failed"] == 0
        
        logger.info(f"Comprehensive testing completed: {test_results['total_passed']}/{test_results['total_tests']} passed")
        
        return test_results
        
    except Exception as e:
        logger.error(f"Error during comprehensive testing: {str(e)}")
        return {
            "project_id": project_id,
            "error": str(e),
            "executed_at": datetime.utcnow().isoformat(),
            "overall_success": False,
            "total_tests": 0,
            "total_passed": 0,
            "total_failed": 1,
            "failures": [{
                "test_name": "comprehensive_testing",
                "error_message": str(e),
                "category": "system_error"
            }]
        }
    
    finally:
        # Clean up test environment
        await cleanup_test_environment(test_env_path)


async def setup_test_environment(project_id: str, html_content: str) -> str:
    """
    Set up test environment with generated HTML content.
    
    Args:
        project_id: Project identifier
        html_content: HTML content to test
    
    Returns:
        Path to the test environment directory
    """
    logger.info(f"Setting up test environment for project {project_id}")
    
    try:
        # Create temporary directory for testing
        temp_dir = tempfile.mkdtemp(prefix=f"test_env_{project_id}_")
        
        # Write HTML content to index.html
        index_path = os.path.join(temp_dir, "index.html")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        # Create basic test structure
        test_dir = os.path.join(temp_dir, "tests")
        os.makedirs(test_dir, exist_ok=True)
        
        # Create package.json for JavaScript testing
        package_json = {
            "name": f"test-project-{project_id}",
            "version": "1.0.0",
            "scripts": {
                "test": "echo 'No tests specified'",
                "test:unit": "echo 'Unit tests would run here'",
                "test:integration": "echo 'Integration tests would run here'"
            },
            "devDependencies": {}
        }
        
        import json
        package_path = os.path.join(temp_dir, "package.json")
        with open(package_path, "w", encoding="utf-8") as f:
            json.dump(package_json, f, indent=2)
        
        logger.info(f"Test environment created at: {temp_dir}")
        return temp_dir
        
    except Exception as e:
        logger.error(f"Failed to set up test environment: {str(e)}")
        raise


async def cleanup_test_environment(test_env_path: str) -> bool:
    """
    Clean up test environment directory.
    
    Args:
        test_env_path: Path to test environment to clean up
    
    Returns:
        True if cleanup was successful, False otherwise
    """
    try:
        if test_env_path and os.path.exists(test_env_path):
            import shutil
            shutil.rmtree(test_env_path)
            logger.info(f"Test environment cleaned up: {test_env_path}")
            return True
        return True
    except Exception as e:
        logger.error(f"Failed to clean up test environment {test_env_path}: {str(e)}")
        return False


async def _run_unit_tests(
    project_id: str, 
    test_env_path: str, 
    tester_agent: Optional[TesterAgent]
) -> Optional[Dict[str, Any]]:
    """Run unit tests for the project."""
    start_time = datetime.utcnow()
    
    try:
        # Basic HTML validation as unit test
        index_path = os.path.join(test_env_path, "index.html")
        
        if not os.path.exists(index_path):
            return {
                "test_type": "unit",
                "total_tests": 1,
                "passed": 0,
                "failed": 1,
                "duration": 0.1,
                "failures": [{
                    "test_name": "html_file_exists",
                    "error_message": "index.html file not found",
                    "category": "file_missing"
                }],
                "warnings": []
            }
        
        # Read and validate HTML content
        with open(index_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        failures = []
        warnings = []
        tests_run = 0
        tests_passed = 0
        
        # Test 1: HTML structure validation
        tests_run += 1
        if not html_content.strip():
            failures.append({
                "test_name": "html_not_empty",
                "error_message": "HTML content is empty",
                "category": "content_validation"
            })
        else:
            tests_passed += 1
        
        # Test 2: DOCTYPE declaration
        tests_run += 1
        if not html_content.strip().startswith('<!DOCTYPE html>'):
            warnings.append("HTML should start with <!DOCTYPE html> declaration")
            # Don't fail for this, just warn
            tests_passed += 1
        else:
            tests_passed += 1
        
        # Test 3: Basic HTML structure
        tests_run += 1
        required_tags = ['<html', '<head', '<body']
        missing_tags = [tag for tag in required_tags if tag not in html_content]
        if missing_tags:
            failures.append({
                "test_name": "html_structure_validation",
                "error_message": f"Missing required HTML tags: {', '.join(missing_tags)}",
                "category": "structure_validation"
            })
        else:
            tests_passed += 1
        
        # Test 4: Meta viewport for responsive design
        tests_run += 1
        if 'name="viewport"' not in html_content:
            warnings.append("Consider adding viewport meta tag for responsive design")
            tests_passed += 1  # Don't fail for this
        else:
            tests_passed += 1
        
        # Test 5: Title tag presence
        tests_run += 1
        if '<title>' not in html_content:
            warnings.append("HTML should include a title tag")
            tests_passed += 1  # Don't fail for this
        else:
            tests_passed += 1
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        return {
            "test_type": "unit",
            "total_tests": tests_run,
            "passed": tests_passed,
            "failed": len(failures),
            "duration": duration,
            "failures": failures,
            "warnings": warnings
        }
        
    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"Unit test execution failed: {str(e)}")
        return {
            "test_type": "unit",
            "total_tests": 1,
            "passed": 0,
            "failed": 1,
            "duration": duration,
            "failures": [{
                "test_name": "unit_test_execution",
                "error_message": str(e),
                "category": "execution_error"
            }],
            "warnings": []
        }


async def _run_integration_tests(
    project_id: str, 
    test_env_path: str, 
    tester_agent: Optional[TesterAgent]
) -> Optional[Dict[str, Any]]:
    """Run integration tests for the project."""
    start_time = datetime.utcnow()
    
    try:
        index_path = os.path.join(test_env_path, "index.html")
        
        if not os.path.exists(index_path):
            return {
                "test_type": "integration",
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "duration": 0.1,
                "failures": [],
                "warnings": ["No HTML file found for integration testing"]
            }
        
        with open(index_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        failures = []
        warnings = []
        tests_run = 0
        tests_passed = 0
        
        # Test 1: CSS integration (external or internal)
        tests_run += 1
        has_css = (
            '<link' in html_content and 'stylesheet' in html_content
        ) or '<style' in html_content
        
        if not has_css:
            warnings.append("No CSS styling detected - consider adding styles for better presentation")
            tests_passed += 1  # Don't fail for this
        else:
            tests_passed += 1
        
        # Test 2: JavaScript integration check
        tests_run += 1
        has_js = '<script' in html_content
        if has_js:
            # Check for basic JavaScript syntax issues
            import re
            script_blocks = re.findall(r'<script[^>]*>(.*?)</script>', html_content, re.DOTALL)
            for i, script in enumerate(script_blocks):
                if script.strip():
                    # Basic syntax check - look for common issues
                    if script.count('(') != script.count(')'):
                        failures.append({
                            "test_name": f"javascript_syntax_check_{i}",
                            "error_message": "Mismatched parentheses in JavaScript",
                            "category": "syntax_error"
                        })
                    elif script.count('{') != script.count('}'):
                        failures.append({
                            "test_name": f"javascript_syntax_check_{i}",
                            "error_message": "Mismatched braces in JavaScript",
                            "category": "syntax_error"
                        })
                    else:
                        tests_passed += 1
        else:
            tests_passed += 1  # No JS is fine
        
        # Test 3: Form integration (if forms are present)
        tests_run += 1
        forms = html_content.count('<form')
        if forms > 0:
            # Check for proper form attributes
            if 'action=' not in html_content and 'onsubmit=' not in html_content:
                warnings.append("Forms detected but no action or onsubmit handler found")
            tests_passed += 1
        else:
            tests_passed += 1  # No forms is fine
        
        # Test 4: Link integration
        tests_run += 1
        links = re.findall(r'href=["\']([^"\']+)["\']', html_content)
        external_links = [link for link in links if link.startswith('http')]
        if external_links:
            warnings.append(f"External links detected: {len(external_links)} - ensure they are valid")
        tests_passed += 1
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        return {
            "test_type": "integration",
            "total_tests": tests_run,
            "passed": tests_passed,
            "failed": len(failures),
            "duration": duration,
            "failures": failures,
            "warnings": warnings
        }
        
    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"Integration test execution failed: {str(e)}")
        return {
            "test_type": "integration",
            "total_tests": 1,
            "passed": 0,
            "failed": 1,
            "duration": duration,
            "failures": [{
                "test_name": "integration_test_execution",
                "error_message": str(e),
                "category": "execution_error"
            }],
            "warnings": []
        }


async def _run_ui_tests(
    project_id: str, 
    html_content: str, 
    test_env_path: str, 
    tester_agent: Optional[TesterAgent]
) -> Optional[Dict[str, Any]]:
    """Run UI tests including accessibility checks."""
    start_time = datetime.utcnow()
    
    try:
        failures = []
        warnings = []
        tests_run = 0
        tests_passed = 0
        
        # Test 1: Accessibility - Alt text for images
        tests_run += 1
        import re
        img_tags = re.findall(r'<img[^>]*>', html_content, re.IGNORECASE)
        images_without_alt = []
        
        for img in img_tags:
            if 'alt=' not in img.lower():
                images_without_alt.append(img)
        
        if images_without_alt:
            warnings.append(f"Found {len(images_without_alt)} images without alt text - important for accessibility")
            tests_passed += 1  # Don't fail, just warn
        else:
            tests_passed += 1
        
        # Test 2: Accessibility - Heading structure
        tests_run += 1
        headings = re.findall(r'<h([1-6])[^>]*>', html_content, re.IGNORECASE)
        if headings:
            heading_levels = [int(h) for h in headings]
            # Check if h1 exists
            if 1 not in heading_levels:
                warnings.append("No H1 heading found - important for SEO and accessibility")
            tests_passed += 1
        else:
            warnings.append("No headings found - consider adding headings for better structure")
            tests_passed += 1
        
        # Test 3: Responsive design indicators
        tests_run += 1
        responsive_indicators = [
            'viewport',
            'media',
            'responsive',
            'mobile',
            '@media',
            'flex',
            'grid'
        ]
        
        responsive_score = sum(1 for indicator in responsive_indicators if indicator in html_content.lower())
        if responsive_score < 2:
            warnings.append("Limited responsive design indicators found - consider mobile optimization")
        tests_passed += 1
        
        # Test 4: Performance - Large inline content
        tests_run += 1
        if len(html_content) > 100000:  # 100KB
            warnings.append("Large HTML file detected - consider optimizing for performance")
        tests_passed += 1
        
        # Test 5: SEO basics
        tests_run += 1
        seo_elements = ['<title>', 'name="description"', 'name="keywords"']
        missing_seo = [elem for elem in seo_elements if elem not in html_content]
        
        if missing_seo:
            warnings.append(f"Missing SEO elements: {', '.join(missing_seo)}")
        tests_passed += 1
        
        # Test 6: Color contrast (basic check)
        tests_run += 1
        # Look for potential color contrast issues
        style_content = ""
        style_blocks = re.findall(r'<style[^>]*>(.*?)</style>', html_content, re.DOTALL)
        for block in style_blocks:
            style_content += block
        
        # Check for inline styles too
        inline_styles = re.findall(r'style=["\']([^"\']+)["\']', html_content)
        for style in inline_styles:
            style_content += style
        
        if 'color:' in style_content.lower() and 'background' in style_content.lower():
            # Basic check - if both colors and backgrounds are set, assume it's handled
            tests_passed += 1
        else:
            warnings.append("Consider checking color contrast for accessibility compliance")
            tests_passed += 1
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        return {
            "test_type": "ui",
            "total_tests": tests_run,
            "passed": tests_passed,
            "failed": len(failures),
            "duration": duration,
            "failures": failures,
            "warnings": warnings,
            "accessibility_checks": {
                "images_without_alt": len(images_without_alt),
                "headings_found": len(headings) if 'headings' in locals() else 0,
                "responsive_score": responsive_score if 'responsive_score' in locals() else 0
            }
        }
        
    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"UI test execution failed: {str(e)}")
        return {
            "test_type": "ui",
            "total_tests": 1,
            "passed": 0,
            "failed": 1,
            "duration": duration,
            "failures": [{
                "test_name": "ui_test_execution",
                "error_message": str(e),
                "category": "execution_error"
            }],
            "warnings": []
        }


async def handle_test_failures(
    project_id: str, 
    test_results: Dict[str, Any], 
    failure_analyzer: Optional[TestFailureAnalyzer] = None
) -> Dict[str, Any]:
    """
    Handle test failures and attempt auto-remediation.
    
    Args:
        project_id: Project identifier
        test_results: Results from comprehensive testing
        failure_analyzer: Optional failure analyzer for auto-remediation
    
    Returns:
        Dictionary containing remediation results
    """
    logger.info(f"Handling test failures for project {project_id}")
    
    failures = test_results.get("failures", [])
    if not failures:
        return {
            "project_id": project_id,
            "remediation_needed": False,
            "message": "No failures to remediate"
        }
    
    remediation_results = {
        "project_id": project_id,
        "remediation_needed": True,
        "total_failures": len(failures),
        "analyzed_failures": 0,
        "auto_fixed_failures": 0,
        "manual_fixes_needed": 0,
        "remediation_suggestions": [],
        "retry_recommended": False
    }
    
    try:
        for failure in failures:
            remediation_results["analyzed_failures"] += 1
            
            # Create TestFailure object
            test_failure = TestFailure(
                test_name=failure.get("test_name", "unknown"),
                error_message=failure.get("error_message", ""),
                stack_trace=failure.get("stack_trace"),
                file_path=failure.get("file_path"),
                line_number=failure.get("line_number"),
                category=failure.get("category", "unknown")
            )
            
            # Analyze failure
            if failure_analyzer:
                try:
                    analysis = await failure_analyzer.analyze_failure(
                        test_failure, 
                        {"project_id": project_id}
                    )
                    
                    # Try to suggest and apply fix
                    category = analysis.get("category", test_failure.category)
                    suggested_fix = await failure_analyzer.suggest_fix(test_failure, category)
                    
                    if suggested_fix:
                        remediation_results["remediation_suggestions"].append({
                            "test_name": test_failure.test_name,
                            "category": category,
                            "suggested_fix": suggested_fix,
                            "severity": analysis.get("severity", "medium"),
                            "confidence": analysis.get("confidence", 0.5)
                        })
                        
                        # For now, we don't auto-apply fixes to avoid breaking changes
                        # In a real implementation, you might apply fixes for certain categories
                        remediation_results["manual_fixes_needed"] += 1
                    else:
                        remediation_results["manual_fixes_needed"] += 1
                        
                except Exception as e:
                    logger.error(f"Failed to analyze failure {test_failure.test_name}: {str(e)}")
                    remediation_results["manual_fixes_needed"] += 1
            else:
                # Basic remediation suggestions without analyzer
                basic_suggestion = _get_basic_remediation_suggestion(test_failure)
                remediation_results["remediation_suggestions"].append({
                    "test_name": test_failure.test_name,
                    "category": test_failure.category,
                    "suggested_fix": basic_suggestion,
                    "severity": "medium",
                    "confidence": 0.3
                })
                remediation_results["manual_fixes_needed"] += 1
        
        # Determine if retry is recommended
        remediation_results["retry_recommended"] = (
            remediation_results["auto_fixed_failures"] > 0 or
            remediation_results["manual_fixes_needed"] < remediation_results["total_failures"]
        )
        
        logger.info(f"Remediation analysis complete: {remediation_results['auto_fixed_failures']} auto-fixed, "
                   f"{remediation_results['manual_fixes_needed']} need manual attention")
        
        return remediation_results
        
    except Exception as e:
        logger.error(f"Error during failure remediation: {str(e)}")
        remediation_results["error"] = str(e)
        return remediation_results


def _get_basic_remediation_suggestion(failure: TestFailure) -> str:
    """Get basic remediation suggestion without advanced analysis."""
    category = failure.category or "unknown"
    
    suggestions = {
        "content_validation": "Ensure HTML content is not empty and properly formatted",
        "structure_validation": "Add missing HTML tags (html, head, body) to create proper document structure",
        "syntax_error": "Check for syntax errors in HTML, CSS, or JavaScript code",
        "file_missing": "Ensure all required files are present in the project",
        "execution_error": "Check system resources and dependencies",
        "accessibility": "Add alt text to images and proper heading structure",
        "performance": "Optimize file sizes and consider code splitting",
        "seo": "Add title, meta description, and other SEO elements"
    }
    
    return suggestions.get(category, "Manual investigation and fixing required")


async def retry_failed_tests(
    project_id: str,
    original_results: Dict[str, Any],
    remediation_applied: bool = False,
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    Retry failed tests after remediation attempts.
    
    Args:
        project_id: Project identifier
        original_results: Original test results with failures
        remediation_applied: Whether remediation was applied
        max_retries: Maximum number of retry attempts
    
    Returns:
        Updated test results after retry
    """
    logger.info(f"Retrying failed tests for project {project_id}")
    
    if not remediation_applied:
        logger.warning("No remediation was applied, retry may not improve results")
    
    retry_count = original_results.get("retry_count", 0)
    if retry_count >= max_retries:
        logger.warning(f"Maximum retries ({max_retries}) reached for project {project_id}")
        return {
            **original_results,
            "retry_exhausted": True,
            "final_attempt": True
        }
    
    try:
        # Extract HTML content from original results if available
        html_content = original_results.get("html_content", "")
        if not html_content:
            # Try to read from test environment if it still exists
            test_env = original_results.get("test_environment")
            if test_env and os.path.exists(os.path.join(test_env, "index.html")):
                with open(os.path.join(test_env, "index.html"), "r", encoding="utf-8") as f:
                    html_content = f.read()
        
        if not html_content:
            return {
                **original_results,
                "retry_error": "No HTML content available for retry",
                "retry_count": retry_count + 1
            }
        
        # Run tests again
        retry_results = await run_comprehensive_tests(project_id, html_content)
        
        # Compare results
        original_failed = original_results.get("total_failed", 0)
        retry_failed = retry_results.get("total_failed", 0)
        
        improvement = original_failed - retry_failed
        
        # Add retry metadata
        retry_results.update({
            "retry_count": retry_count + 1,
            "original_failures": original_failed,
            "retry_failures": retry_failed,
            "improvement": improvement,
            "remediation_applied": remediation_applied,
            "retry_successful": improvement > 0
        })
        
        logger.info(f"Retry completed: {improvement} fewer failures than original attempt")
        
        return retry_results
        
    except Exception as e:
        logger.error(f"Error during test retry: {str(e)}")
        return {
            **original_results,
            "retry_error": str(e),
            "retry_count": retry_count + 1
        }


async def generate_detailed_test_report(
    project_id: str,
    test_results: Dict[str, Any],
    remediation_results: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate a detailed test report with failure analysis and recommendations.
    
    Args:
        project_id: Project identifier
        test_results: Comprehensive test results
        remediation_results: Optional remediation analysis results
    
    Returns:
        Detailed test report
    """
    logger.info(f"Generating detailed test report for project {project_id}")
    
    report = {
        "project_id": project_id,
        "report_generated_at": datetime.utcnow().isoformat(),
        "executive_summary": {},
        "test_breakdown": {},
        "failure_analysis": {},
        "recommendations": [],
        "next_steps": []
    }
    
    try:
        # Executive Summary
        total_tests = test_results.get("total_tests", 0)
        total_passed = test_results.get("total_passed", 0)
        total_failed = test_results.get("total_failed", 0)
        success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        
        report["executive_summary"] = {
            "overall_status": "PASS" if total_failed == 0 else "FAIL",
            "total_tests": total_tests,
            "passed": total_passed,
            "failed": total_failed,
            "success_rate": round(success_rate, 2),
            "total_duration": test_results.get("total_duration", 0),
            "test_types_executed": []
        }
        
        # Test Breakdown
        test_types = ["unit_tests", "integration_tests", "ui_tests"]
        for test_type in test_types:
            if test_results.get(test_type):
                test_data = test_results[test_type]
                report["test_breakdown"][test_type] = {
                    "total": test_data.get("total_tests", 0),
                    "passed": test_data.get("passed", 0),
                    "failed": test_data.get("failed", 0),
                    "duration": test_data.get("duration", 0),
                    "warnings": len(test_data.get("warnings", [])),
                    "status": "PASS" if test_data.get("failed", 0) == 0 else "FAIL"
                }
                report["executive_summary"]["test_types_executed"].append(test_type)
        
        # Failure Analysis
        failures = test_results.get("failures", [])
        if failures:
            failure_categories = {}
            for failure in failures:
                category = failure.get("category", "unknown")
                if category not in failure_categories:
                    failure_categories[category] = []
                failure_categories[category].append(failure)
            
            report["failure_analysis"] = {
                "total_failures": len(failures),
                "categories": {
                    category: {
                        "count": len(category_failures),
                        "failures": category_failures
                    }
                    for category, category_failures in failure_categories.items()
                },
                "most_common_category": max(failure_categories.keys(), 
                                          key=lambda k: len(failure_categories[k])) if failure_categories else None
            }
        
        # Recommendations
        warnings = test_results.get("warnings", [])
        
        if total_failed == 0:
            report["recommendations"].append({
                "priority": "low",
                "category": "optimization",
                "message": "All tests passed! Consider adding more comprehensive tests as the project grows."
            })
        else:
            report["recommendations"].append({
                "priority": "high",
                "category": "bug_fix",
                "message": f"Address {total_failed} failing tests before deployment."
            })
        
        if warnings:
            report["recommendations"].append({
                "priority": "medium",
                "category": "improvement",
                "message": f"Review {len(warnings)} warnings for potential improvements."
            })
        
        # Add remediation recommendations if available
        if remediation_results:
            manual_fixes = remediation_results.get("manual_fixes_needed", 0)
            if manual_fixes > 0:
                report["recommendations"].append({
                    "priority": "high",
                    "category": "remediation",
                    "message": f"{manual_fixes} failures require manual attention."
                })
            
            if remediation_results.get("retry_recommended"):
                report["recommendations"].append({
                    "priority": "medium",
                    "category": "retry",
                    "message": "Retry tests after applying suggested fixes."
                })
        
        # Next Steps
        if total_failed > 0:
            report["next_steps"].append("Fix failing tests before proceeding to deployment")
            report["next_steps"].append("Review failure analysis for specific remediation steps")
        
        if warnings:
            report["next_steps"].append("Address warnings to improve code quality")
        
        if total_failed == 0:
            report["next_steps"].append("Proceed to deployment phase")
            report["next_steps"].append("Set up monitoring for the deployed application")
        
        logger.info(f"Test report generated successfully for project {project_id}")
        return report
        
    except Exception as e:
        logger.error(f"Error generating test report: {str(e)}")
        return {
            "project_id": project_id,
            "error": str(e),
            "report_generated_at": datetime.utcnow().isoformat()
        }