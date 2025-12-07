"""
Safety Manager
Coordinates safety guardrails and logs safety events.
"""

from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
import json
import asyncio

from src.guardrails.input_guardrail import InputGuardrail
from src.guardrails.output_guardrail import OutputGuardrail
from src.guardrails.llm_safety_helper import create_llm_client


def _run_async_in_thread(coro):
    """Helper to run async code in a new event loop in a thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class SafetyManager:
    """
    Manages safety guardrails for the multi-agent system.
    
    Uses custom LLM-based safety checks with input and output guardrails.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize safety manager.

        Args:
            config: Safety configuration
        """
        self.config = config
        self.enabled = config.get("enabled", True)
        self.log_events = config.get("log_events", True)
        self.logger = logging.getLogger("safety")

        # Safety event log
        self.safety_events: List[Dict[str, Any]] = []

        # Prohibited categories
        self.prohibited_categories = config.get("prohibited_categories", [
            "harmful_content",
            "personal_attacks",
            "misinformation",
            "off_topic_queries"
        ])

        # Violation response strategy
        self.on_violation = config.get("on_violation", {})

        # Initialize LLM client for safety checks
        self.llm_client = create_llm_client(config)
        
        # Initialize input and output guardrails
        self.input_guardrail = InputGuardrail(config)
        self.output_guardrail = OutputGuardrail(config)
        
        # Get system topic from config (handle both nested and flat config structures)
        system_config = config.get("system", {})
        if isinstance(system_config, dict):
            self.topic = system_config.get("topic", "HCI Research")
        else:
            # If config structure is different, try to get from root level
            self.topic = config.get("topic", "HCI Research")

    def check_input_safety(self, query: str) -> Dict[str, Any]:
        """
        Check if input query is safe to process.

        Args:
            query: User query to check

        Returns:
            Dictionary with 'safe' boolean and optional 'violations' list
        """
        if not self.enabled:
            return {"safe": True}

        # Use input guardrail for validation
        validation_result = self.input_guardrail.validate(query)
        
        if not validation_result.get("valid", True):
            violations = validation_result.get("violations", [])
            is_safe = False
        else:
            # Additional LLM-based safety check if client available
            if self.llm_client:
                try:
                    # Run async LLM check
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If already in async context, create new loop in thread
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            future = pool.submit(_run_async_in_thread, self._check_input_llm(query))
                            llm_result = future.result()
                    else:
                        llm_result = loop.run_until_complete(self._check_input_llm(query))
                    
                    if not llm_result.get("safe", True):
                        violations = [{
                            "category": llm_result.get("category", "unknown"),
                            "reason": llm_result.get("reasoning", "LLM safety check failed"),
                            "severity": llm_result.get("severity", "medium")
                        }]
                        is_safe = False
                    else:
                        violations = []
                        is_safe = True
                except Exception as e:
                    self.logger.warning(f"LLM safety check failed, using guardrail result: {e}")
                    violations = validation_result.get("violations", [])
                    is_safe = len(violations) == 0
            else:
                violations = validation_result.get("violations", [])
                is_safe = len(violations) == 0

        # Log safety event
        if not is_safe and self.log_events:
            self._log_safety_event("input", query, violations, is_safe)

        return {
            "safe": is_safe,
            "violations": violations,
            "sanitized_query": validation_result.get("sanitized_input", query) if not is_safe else query
        }
    
    async def _check_input_llm(self, query: str) -> Dict[str, Any]:
        """Async helper for LLM input safety check."""
        from src.guardrails.llm_safety_helper import check_content_safety_llm
        return await check_content_safety_llm(
            self.llm_client,
            query,
            "input",
            self.config,
            self.topic
        )

    def check_output_safety(self, response: str, sources: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Check if output response is safe to return.

        Args:
            response: Generated response to check
            sources: Optional list of sources used (for fact-checking)

        Returns:
            Dictionary with 'safe' boolean and optional 'violations' list
        """
        if not self.enabled:
            return {"safe": True, "response": response}

        # Use output guardrail for validation
        validation_result = self.output_guardrail.validate(response, sources)
        
        violations = validation_result.get("violations", [])
        
        # Additional LLM-based safety check if client available
        if self.llm_client:
            try:
                # Run async LLM check
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(_run_async_in_thread, self._check_output_llm(response))
                        llm_result = future.result()
                else:
                    llm_result = loop.run_until_complete(self._check_output_llm(response))
                
                if not llm_result.get("safe", True):
                    llm_violations = llm_result.get("violations", [])
                    for v in llm_violations:
                        violations.append({
                            "category": "harmful_content",
                            "reason": llm_result.get("reasoning", "LLM detected unsafe content"),
                            "severity": llm_result.get("severity", "medium"),
                            "validator": "llm_safety_check"
                        })
            except Exception as e:
                self.logger.warning(f"LLM output safety check failed, using guardrail result: {e}")

        is_safe = len(violations) == 0

        # Log safety event
        if not is_safe and self.log_events:
            self._log_safety_event("output", response, violations, is_safe)

        result = {
            "safe": is_safe,
            "violations": violations,
            "response": response
        }

        # Apply sanitization if configured
        if not is_safe:
            action = self.on_violation.get("action", "refuse")
            if action == "sanitize":
                result["response"] = validation_result.get("sanitized_output", response)
            elif action == "refuse":
                result["response"] = self.on_violation.get(
                    "message",
                    "I cannot provide this response due to safety policies."
                )

        return result
    
    async def _check_output_llm(self, response: str) -> Dict[str, Any]:
        """Async helper for LLM output safety check."""
        from src.guardrails.llm_safety_helper import check_content_safety_llm
        return await check_content_safety_llm(
            self.llm_client,
            response,
            "output",
            self.config,
            self.topic
        )

    def _sanitize_response(self, response: str, violations: List[Dict[str, Any]]) -> str:
        """
        Sanitize response by removing or redacting unsafe content.
        """
        # Use output guardrail's sanitization
        sanitized = self.output_guardrail._sanitize(response, violations)
        return sanitized

    def _log_safety_event(
        self,
        event_type: str,
        content: str,
        violations: List[Dict[str, Any]],
        is_safe: bool
    ):
        """
        Log a safety event.

        Args:
            event_type: "input" or "output"
            content: The content that was checked
            violations: List of violations found
            is_safe: Whether content passed safety checks
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "safe": is_safe,
            "violations": violations,
            "content_preview": content[:100] + "..." if len(content) > 100 else content
        }

        self.safety_events.append(event)
        self.logger.warning(f"Safety event: {event_type} - safe={is_safe}")

        # Write to safety log file if configured
        log_file = self.config.get("safety_log_file")
        if log_file and self.log_events:
            try:
                with open(log_file, "a") as f:
                    f.write(json.dumps(event) + "\n")
            except Exception as e:
                self.logger.error(f"Failed to write safety log: {e}")

    def get_safety_events(self) -> List[Dict[str, Any]]:
        """Get all logged safety events."""
        return self.safety_events

    def get_safety_stats(self) -> Dict[str, Any]:
        """
        Get statistics about safety events.

        Returns:
            Dictionary with safety statistics
        """
        total = len(self.safety_events)
        input_events = sum(1 for e in self.safety_events if e["type"] == "input")
        output_events = sum(1 for e in self.safety_events if e["type"] == "output")
        violations = sum(1 for e in self.safety_events if not e["safe"])

        return {
            "total_events": total,
            "input_checks": input_events,
            "output_checks": output_events,
            "violations": violations,
            "violation_rate": violations / total if total > 0 else 0
        }

    def clear_events(self):
        """Clear safety event log."""
        self.safety_events = []
