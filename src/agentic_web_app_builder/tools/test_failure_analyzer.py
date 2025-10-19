"""Test failure analysis and auto-remediation system."""

import asyncio
import os
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

from .testing_interfaces import TestFailureAnalyzer, TestFailure
from ..tools.llm_service import LLMService


class IntelligentTestFailureAnalyzer(TestFailureAnalyzer):
    """Intelligent test failure analyzer using LLM for analysis and remediation."""
    
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
        self.logger = None
        
        # Common failure patterns and their categories
        self.failure_patterns = {
            "syntax_error": [
                r"SyntaxError",
                r"Unexpected token",
                r"Parse error",
                r"Invalid syntax"
            ],
            "type_error": [
                r"TypeError",
                r"Cannot read property",
                r"is not a function",
                r"undefined is not an object"
            ],
            "reference_error": [
                r"ReferenceError",
                r"is not defined",
                r"Cannot access before initialization"
            ],
            "assertion_error": [
                r"AssertionError",
                r"Expected.*but got",
                r"toBe.*received",
                r"toEqual.*received"
            ],
            "timeout_error": [
                r"TimeoutError",
                r"Test timeout",
                r"exceeded timeout",
                r"Timeout of.*exceeded"
            ],
            "network_error": [
                r"NetworkError",
                r"fetch failed",
                r"ECONNREFUSED",
                r"Request failed"
            ],
            "dom_error": [
                r"Element not found",
                r"querySelector.*null",
                r"Cannot find element",
                r"Element is not visible"
            ]
        }
        
        # Auto-fix templates for common issues
        self.fix_templates = {
            "syntax_error": {
                "missing_semicolon": "Add missing semicolon",
                "missing_bracket": "Add missing bracket or parenthesis",
                "invalid_import": "Fix import statement syntax"
            },
            "type_error": {
                "undefined_property": "Add null/undefined check",
                "wrong_function_call": "Fix function call syntax",
                "missing_await": "Add await keyword for async function"
            },
            "reference_error": {
                "undefined_variable": "Define the variable or import it",
                "wrong_scope": "Move variable declaration to correct scope"
            },
            "assertion_error": {
                "wrong_expectation": "Update test expectation to match actual behavior",
                "data_mismatch": "Update test data or fix implementation"
            },
            "timeout_error": {
                "increase_timeout": "Increase test timeout value",
                "add_wait": "Add proper wait conditions"
            },
            "network_error": {
                "mock_request": "Add request mocking",
                "fix_endpoint": "Fix API endpoint URL"
            },
            "dom_error": {
                "wait_for_element": "Add wait for element to be visible",
                "fix_selector": "Fix CSS selector"
            }
        }
    
    async def analyze_failure(self, failure: TestFailure, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a test failure and provide detailed analysis."""
        # Categorize the failure
        category = await self.categorize_failure(failure)
        
        # Extract relevant code context
        code_context = await self._extract_code_context(failure, context)
        
        # Use LLM for detailed analysis
        analysis_prompt = self._create_analysis_prompt(failure, category, code_context)
        
        try:
            llm_analysis = await self.llm_service.generate_completion(
                prompt=analysis_prompt,
                max_tokens=500,
                temperature=0.1
            )
            
            analysis = {
                "category": category,
                "severity": self._assess_severity(failure, category),
                "root_cause": self._extract_root_cause(failure, category),
                "affected_components": self._identify_affected_components(failure, context),
                "llm_analysis": llm_analysis,
                "confidence": self._calculate_confidence(failure, category),
                "analyzed_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            # Fallback to rule-based analysis if LLM fails
            analysis = {
                "category": category,
                "severity": self._assess_severity(failure, category),
                "root_cause": self._extract_root_cause(failure, category),
                "affected_components": self._identify_affected_components(failure, context),
                "llm_analysis": f"LLM analysis failed: {str(e)}",
                "confidence": 0.6,  # Lower confidence without LLM
                "analyzed_at": datetime.utcnow().isoformat()
            }
        
        return analysis
    
    async def categorize_failure(self, failure: TestFailure) -> str:
        """Categorize the type of test failure."""
        error_message = failure.error_message.lower()
        stack_trace = (failure.stack_trace or "").lower()
        
        # Check against known patterns
        for category, patterns in self.failure_patterns.items():
            for pattern in patterns:
                if re.search(pattern.lower(), error_message) or re.search(pattern.lower(), stack_trace):
                    return category
        
        # Default category
        return "unknown_error"
    
    async def suggest_fix(self, failure: TestFailure, category: str) -> Optional[str]:
        """Suggest an automatic fix for the failure."""
        # Get specific fix suggestions based on category
        if category not in self.fix_templates:
            return None
        
        # Use LLM to generate specific fix
        fix_prompt = self._create_fix_prompt(failure, category)
        
        try:
            suggested_fix = await self.llm_service.generate_completion(
                prompt=fix_prompt,
                max_tokens=300,
                temperature=0.1
            )
            
            return suggested_fix.strip()
            
        except Exception as e:
            # Fallback to template-based fix
            return self._get_template_fix(failure, category)
    
    async def apply_fix(self, failure: TestFailure, fix: str, project_path: str) -> bool:
        """Apply an automatic fix to the codebase."""
        if not failure.file_path or not fix:
            return False
        
        file_path = os.path.join(project_path, failure.file_path)
        
        if not os.path.exists(file_path):
            return False
        
        try:
            # Read the file
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Apply the fix based on the fix type
            modified_content = await self._apply_fix_to_content(content, failure, fix)
            
            if modified_content != content:
                # Create backup
                backup_path = f"{file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # Write the fixed content
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(modified_content)
                
                return True
            
        except Exception as e:
            # Log error but don't fail
            return False
        
        return False
    
    def _create_analysis_prompt(self, failure: TestFailure, category: str, code_context: str) -> str:
        """Create a prompt for LLM analysis of the test failure."""
        return f"""
Analyze this test failure and provide insights:

Test Name: {failure.test_name}
Error Message: {failure.error_message}
Category: {category}
File: {failure.file_path}
Line: {failure.line_number}

Stack Trace:
{failure.stack_trace or 'Not available'}

Code Context:
{code_context}

Please provide:
1. Root cause analysis
2. Impact assessment
3. Recommended solution approach
4. Prevention strategies

Keep the analysis concise and actionable.
"""
    
    def _create_fix_prompt(self, failure: TestFailure, category: str) -> str:
        """Create a prompt for LLM to suggest a specific fix."""
        return f"""
Generate a specific code fix for this test failure:

Test: {failure.test_name}
Error: {failure.error_message}
Category: {category}
File: {failure.file_path}
Line: {failure.line_number}

Expected: {failure.expected or 'Not specified'}
Actual: {failure.actual or 'Not specified'}

Provide a specific, minimal code change that would fix this issue.
Focus on the exact line or lines that need to be modified.
Format as a clear instruction for automated application.
"""
    
    async def _extract_code_context(self, failure: TestFailure, context: Dict[str, Any]) -> str:
        """Extract relevant code context around the failure."""
        if not failure.file_path or not failure.line_number:
            return "Code context not available"
        
        project_path = context.get("project_path", ".")
        file_path = os.path.join(project_path, failure.file_path)
        
        if not os.path.exists(file_path):
            return "File not found"
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Extract context around the error line
            line_num = failure.line_number - 1  # Convert to 0-based index
            start_line = max(0, line_num - 5)
            end_line = min(len(lines), line_num + 6)
            
            context_lines = []
            for i in range(start_line, end_line):
                marker = ">>> " if i == line_num else "    "
                context_lines.append(f"{marker}{i+1}: {lines[i].rstrip()}")
            
            return "\n".join(context_lines)
            
        except Exception:
            return "Could not extract code context"
    
    def _assess_severity(self, failure: TestFailure, category: str) -> str:
        """Assess the severity of the test failure."""
        severity_map = {
            "syntax_error": "high",
            "type_error": "high",
            "reference_error": "high",
            "assertion_error": "medium",
            "timeout_error": "medium",
            "network_error": "low",
            "dom_error": "medium",
            "unknown_error": "medium"
        }
        
        return severity_map.get(category, "medium")
    
    def _extract_root_cause(self, failure: TestFailure, category: str) -> str:
        """Extract the likely root cause of the failure."""
        root_causes = {
            "syntax_error": "Code syntax is invalid",
            "type_error": "Incorrect data type usage",
            "reference_error": "Variable or function not defined",
            "assertion_error": "Test expectation doesn't match actual behavior",
            "timeout_error": "Operation took longer than expected",
            "network_error": "Network request failed",
            "dom_error": "DOM element not found or not accessible",
            "unknown_error": "Unidentified error condition"
        }
        
        return root_causes.get(category, "Unknown root cause")
    
    def _identify_affected_components(self, failure: TestFailure, context: Dict[str, Any]) -> List[str]:
        """Identify components affected by the failure."""
        components = []
        
        if failure.file_path:
            # Extract component name from file path
            file_name = os.path.basename(failure.file_path)
            component_name = file_name.split('.')[0]
            components.append(component_name)
        
        # Look for related components in error message
        error_message = failure.error_message.lower()
        if "component" in error_message:
            # Try to extract component names
            import re
            component_matches = re.findall(r'(\w+)component', error_message)
            components.extend(component_matches)
        
        return list(set(components))  # Remove duplicates
    
    def _calculate_confidence(self, failure: TestFailure, category: str) -> float:
        """Calculate confidence in the analysis."""
        confidence = 0.5  # Base confidence
        
        # Increase confidence based on available information
        if failure.stack_trace:
            confidence += 0.2
        
        if failure.line_number:
            confidence += 0.1
        
        if category != "unknown_error":
            confidence += 0.2
        
        return min(confidence, 1.0)
    
    def _get_template_fix(self, failure: TestFailure, category: str) -> Optional[str]:
        """Get a template-based fix suggestion."""
        if category not in self.fix_templates:
            return None
        
        # Simple heuristic to choose appropriate template
        error_message = failure.error_message.lower()
        
        for fix_type, description in self.fix_templates[category].items():
            if any(keyword in error_message for keyword in fix_type.split('_')):
                return description
        
        # Return first available fix for the category
        fixes = list(self.fix_templates[category].values())
        return fixes[0] if fixes else None
    
    async def _apply_fix_to_content(self, content: str, failure: TestFailure, fix: str) -> str:
        """Apply the fix to the file content."""
        lines = content.split('\n')
        
        if not failure.line_number or failure.line_number > len(lines):
            return content
        
        line_index = failure.line_number - 1
        original_line = lines[line_index]
        
        # Apply different types of fixes based on the fix description
        if "add missing semicolon" in fix.lower():
            if not original_line.rstrip().endswith(';'):
                lines[line_index] = original_line.rstrip() + ';'
        
        elif "add null/undefined check" in fix.lower():
            # Add a simple null check
            indentation = len(original_line) - len(original_line.lstrip())
            null_check = ' ' * indentation + f"if ({self._extract_variable_name(original_line)}) {{"
            lines.insert(line_index, null_check)
            lines.insert(line_index + 2, ' ' * indentation + '}')
        
        elif "add await keyword" in fix.lower():
            if "await" not in original_line and ("fetch" in original_line or "async" in original_line):
                lines[line_index] = original_line.replace("=", "= await", 1)
        
        elif "increase test timeout" in fix.lower():
            # Look for timeout configuration and increase it
            if "timeout" in original_line:
                import re
                timeout_match = re.search(r'timeout[:\s]*(\d+)', original_line)
                if timeout_match:
                    old_timeout = int(timeout_match.group(1))
                    new_timeout = old_timeout * 2
                    lines[line_index] = original_line.replace(str(old_timeout), str(new_timeout))
        
        elif "add wait for element" in fix.lower():
            # Add wait condition for UI tests
            if "querySelector" in original_line or "getByRole" in original_line:
                indentation = len(original_line) - len(original_line.lstrip())
                wait_line = ' ' * indentation + "await page.waitForSelector('selector', { visible: true });"
                lines.insert(line_index, wait_line)
        
        return '\n'.join(lines)
    
    def _extract_variable_name(self, line: str) -> str:
        """Extract variable name from a line of code."""
        # Simple extraction - look for common patterns
        import re
        
        # Look for property access patterns
        property_match = re.search(r'(\w+)\.\w+', line)
        if property_match:
            return property_match.group(1)
        
        # Look for variable assignments
        assignment_match = re.search(r'(\w+)\s*=', line)
        if assignment_match:
            return assignment_match.group(1)
        
        # Default fallback
        return "variable"