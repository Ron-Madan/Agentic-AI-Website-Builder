"""Factory for creating and configuring the Tester Agent with all its tools."""

from typing import Optional

from .tester import TesterAgent
from ..tools.unit_testing import JestVitestTool
from ..tools.integration_testing import CypressPlaywrightTool
from ..tools.ui_testing import PlaywrightUITool
from ..tools.test_failure_analyzer import IntelligentTestFailureAnalyzer
from ..tools.llm_service import LLMService
from ..core.state_manager import StateManager


class TesterAgentFactory:
    """Factory for creating fully configured Tester Agent instances."""
    
    @staticmethod
    def create_tester_agent(
        state_manager: StateManager,
        llm_service: Optional[LLMService] = None
    ) -> TesterAgent:
        """Create a fully configured Tester Agent with all testing tools."""
        
        # Create the main tester agent
        tester_agent = TesterAgent(state_manager)
        
        # Create testing tools
        unit_test_tool = JestVitestTool()
        integration_test_tool = CypressPlaywrightTool()
        ui_test_tool = PlaywrightUITool()
        
        # Create failure analyzer (with or without LLM)
        if llm_service:
            failure_analyzer = IntelligentTestFailureAnalyzer(llm_service)
        else:
            # Create a basic failure analyzer without LLM
            failure_analyzer = BasicTestFailureAnalyzer()
        
        # Configure the tester agent with all tools
        tester_agent.set_tools(
            unit_test_tool=unit_test_tool,
            integration_test_tool=integration_test_tool,
            ui_test_tool=ui_test_tool,
            failure_analyzer=failure_analyzer
        )
        
        return tester_agent
    
    @staticmethod
    def create_unit_test_tool() -> JestVitestTool:
        """Create a standalone unit testing tool."""
        return JestVitestTool()
    
    @staticmethod
    def create_integration_test_tool() -> CypressPlaywrightTool:
        """Create a standalone integration testing tool."""
        return CypressPlaywrightTool()
    
    @staticmethod
    def create_ui_test_tool() -> PlaywrightUITool:
        """Create a standalone UI testing tool."""
        return PlaywrightUITool()
    
    @staticmethod
    def create_failure_analyzer(llm_service: Optional[LLMService] = None) -> 'TestFailureAnalyzer':
        """Create a test failure analyzer."""
        if llm_service:
            return IntelligentTestFailureAnalyzer(llm_service)
        else:
            return BasicTestFailureAnalyzer()


class BasicTestFailureAnalyzer:
    """Basic test failure analyzer without LLM capabilities."""
    
    def __init__(self):
        self.failure_patterns = {
            "syntax_error": ["SyntaxError", "Unexpected token", "Parse error"],
            "type_error": ["TypeError", "Cannot read property", "is not a function"],
            "reference_error": ["ReferenceError", "is not defined"],
            "assertion_error": ["AssertionError", "Expected.*but got", "toBe.*received"],
            "timeout_error": ["TimeoutError", "Test timeout", "exceeded timeout"],
            "network_error": ["NetworkError", "fetch failed", "ECONNREFUSED"],
            "dom_error": ["Element not found", "querySelector.*null", "Cannot find element"]
        }
    
    async def analyze_failure(self, failure, context):
        """Basic failure analysis without LLM."""
        category = await self.categorize_failure(failure)
        
        return {
            "category": category,
            "severity": self._assess_severity(category),
            "root_cause": self._get_root_cause(category),
            "confidence": 0.6,
            "analyzed_at": "basic_analysis"
        }
    
    async def categorize_failure(self, failure):
        """Categorize failure using pattern matching."""
        error_message = failure.error_message.lower()
        
        for category, patterns in self.failure_patterns.items():
            for pattern in patterns:
                if pattern.lower() in error_message:
                    return category
        
        return "unknown_error"
    
    async def suggest_fix(self, failure, category):
        """Suggest basic fixes."""
        fix_suggestions = {
            "syntax_error": "Check for missing semicolons, brackets, or quotes",
            "type_error": "Verify variable types and function calls",
            "reference_error": "Ensure variables are defined and imported",
            "assertion_error": "Update test expectations or fix implementation",
            "timeout_error": "Increase timeout or optimize performance",
            "network_error": "Check network connectivity and endpoints",
            "dom_error": "Verify element selectors and wait conditions"
        }
        
        return fix_suggestions.get(category, "Manual investigation required")
    
    async def apply_fix(self, failure, fix, project_path):
        """Basic fix application - always returns False for manual fixes."""
        return False
    
    def _assess_severity(self, category):
        """Assess failure severity."""
        high_severity = ["syntax_error", "type_error", "reference_error"]
        return "high" if category in high_severity else "medium"
    
    def _get_root_cause(self, category):
        """Get basic root cause description."""
        causes = {
            "syntax_error": "Invalid code syntax",
            "type_error": "Type mismatch or undefined property",
            "reference_error": "Undefined variable or function",
            "assertion_error": "Test expectation mismatch",
            "timeout_error": "Operation timeout",
            "network_error": "Network connectivity issue",
            "dom_error": "DOM element access issue"
        }
        
        return causes.get(category, "Unknown issue")