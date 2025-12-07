"""
Input Guardrail
Checks user inputs for safety violations.
"""

from typing import Dict, Any, List
import logging
import asyncio

from src.guardrails.llm_safety_helper import create_llm_client, check_relevance_llm


def _run_async_in_thread(coro):
    """Helper to run async code in a new event loop in a thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class InputGuardrail:
    """
    Guardrail for checking input safety.
    
    Uses LLM-based checks combined with pattern matching for comprehensive validation.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize input guardrail.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger("safety.input_guardrail")
        
        # Initialize LLM client
        self.llm_client = create_llm_client(config)
        
        # Get system topic from config (handle both nested and flat config structures)
        system_config = config.get("system", {})
        if isinstance(system_config, dict):
            self.topic = system_config.get("topic", "HCI Research")
        else:
            # If config structure is different, try to get from root level
            self.topic = config.get("topic", "HCI Research")

    def validate(self, query: str) -> Dict[str, Any]:
        """
        Validate input query.

        Args:
            query: User input to validate

        Returns:
            Validation result with 'valid' boolean and 'violations' list
        """
        violations = []

        # Basic length checks
        if len(query) < 5:
            violations.append({
                "validator": "length",
                "reason": "Query too short (minimum 5 characters)",
                "severity": "low"
            })

        if len(query) > 2000:
            violations.append({
                "validator": "length",
                "reason": "Query too long (maximum 2000 characters)",
                "severity": "medium"
            })

        # Check for prompt injection
        injection_violations = self._check_prompt_injection(query)
        violations.extend(injection_violations)

        # Check for toxic language (if LLM available)
        if self.llm_client:
            try:
                toxic_violations = self._check_toxic_language(query)
                violations.extend(toxic_violations)
            except Exception as e:
                self.logger.warning(f"Toxic language check failed: {e}")

        # Check relevance to topic (if LLM available)
        if self.llm_client:
            try:
                relevance_violations = self._check_relevance(query)
                violations.extend(relevance_violations)
            except Exception as e:
                self.logger.warning(f"Relevance check failed: {e}")

        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "sanitized_input": query  # Could be modified version
        }

    def _check_toxic_language(self, text: str) -> List[Dict[str, Any]]:
        """
        Check for toxic/harmful language using LLM.
        """
        violations = []
        
        if not self.llm_client:
            return violations
        
        try:
            # Use LLM to check for toxic language
            from src.guardrails.llm_safety_helper import check_content_safety_llm
            
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        _run_async_in_thread,
                        check_content_safety_llm(
                            self.llm_client,
                            text,
                            "input",
                            self.config,
                            self.topic
                        )
                    )
                    result = future.result()
            else:
                result = loop.run_until_complete(
                    check_content_safety_llm(
                        self.llm_client,
                        text,
                        "input",
                        self.config,
                        self.topic
                    )
                )
            
            if not result.get("safe", True):
                category = result.get("category", "harmful_content")
                if category == "HARMFUL":
                    violations.append({
                        "validator": "toxic_language",
                        "reason": result.get("reasoning", "Contains toxic or harmful language"),
                        "severity": result.get("severity", "high")
                    })
        except Exception as e:
            self.logger.error(f"Error in toxic language check: {e}")
        
        return violations

    def _check_prompt_injection(self, text: str) -> List[Dict[str, Any]]:
        """
        Check for prompt injection attempts using pattern matching and LLM verification.
        """
        violations = []
        
        # Check for common prompt injection patterns
        injection_patterns = [
            "ignore previous instructions",
            "disregard",
            "forget everything",
            "system:",
            "sudo",
            "override",
            "new instructions",
            "you are now",
            "pretend to be",
            "act as if",
        ]

        found_patterns = []
        for pattern in injection_patterns:
            if pattern.lower() in text.lower():
                found_patterns.append(pattern)
        
        # If patterns found, verify with LLM if available
        if found_patterns:
            if self.llm_client:
                try:
                    from src.guardrails.llm_safety_helper import check_content_safety_llm
                    
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            future = pool.submit(
                                _run_async_in_thread,
                                check_content_safety_llm(
                                    self.llm_client,
                                    text,
                                    "input",
                                    self.config,
                                    self.topic
                                )
                            )
                            result = future.result()
                    else:
                        result = loop.run_until_complete(
                            check_content_safety_llm(
                                self.llm_client,
                                text,
                                "input",
                                self.config,
                                self.topic
                            )
                        )
                    
                    if result.get("category") == "PROMPT_INJECTION":
                        violations.append({
                            "validator": "prompt_injection",
                            "reason": result.get("reasoning", f"Detected prompt injection patterns: {', '.join(found_patterns)}"),
                            "severity": "high"
                        })
                except Exception as e:
                    self.logger.warning(f"LLM prompt injection check failed, using pattern match: {e}")
                    # Fallback to pattern-based detection
                    violations.append({
                        "validator": "prompt_injection",
                        "reason": f"Potential prompt injection patterns detected: {', '.join(found_patterns)}",
                        "severity": "high"
                    })
            else:
                # No LLM, use pattern-based detection
                violations.append({
                    "validator": "prompt_injection",
                    "reason": f"Potential prompt injection patterns detected: {', '.join(found_patterns)}",
                    "severity": "high"
                })

        return violations

    def _check_relevance(self, query: str) -> List[Dict[str, Any]]:
        """
        Check if query is relevant to the system's topic using LLM.
        """
        violations = []
        
        if not self.llm_client:
            return violations
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(_run_async_in_thread, self._check_relevance_async(query))
                    result = future.result()
            else:
                result = loop.run_until_complete(self._check_relevance_async(query))
            
            if not result.get("relevant", True):
                confidence = result.get("confidence", 0.5)
                if confidence < 0.3:  # Low confidence that it's relevant
                    violations.append({
                        "validator": "relevance",
                        "reason": result.get("reasoning", f"Query may not be relevant to {self.topic}"),
                        "severity": "low"
                    })
        except Exception as e:
            self.logger.error(f"Error in relevance check: {e}")
        
        return violations
    
    async def _check_relevance_async(self, query: str) -> Dict[str, Any]:
        """Async helper for relevance check."""
        return await check_relevance_llm(self.llm_client, query, self.topic, self.config)
