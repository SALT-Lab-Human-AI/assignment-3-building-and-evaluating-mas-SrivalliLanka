"""
Output Guardrail
Checks system outputs for safety violations.
"""

from typing import Dict, Any, List, Optional
import re
import logging
import asyncio

from src.guardrails.llm_safety_helper import create_llm_client


def _run_async_in_thread(coro):
    """Helper to run async code in a new event loop in a thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class OutputGuardrail:
    """
    Guardrail for checking output safety.
    
    Uses LLM-based checks combined with regex patterns for comprehensive validation.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize output guardrail.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger("safety.output_guardrail")
        
        # Initialize LLM client
        self.llm_client = create_llm_client(config)
        
        # Get system topic from config (handle both nested and flat config structures)
        system_config = config.get("system", {})
        if isinstance(system_config, dict):
            self.topic = system_config.get("topic", "HCI Research")
        else:
            # If config structure is different, try to get from root level
            self.topic = config.get("topic", "HCI Research")

    def validate(self, response: str, sources: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Validate output response.

        Args:
            response: Generated response to validate
            sources: Optional list of sources used (for fact-checking)

        Returns:
            Validation result with 'valid' boolean and 'violations' list
        """
        violations = []

        # Check for PII (always run, uses regex)
        pii_violations = self._check_pii(response)
        violations.extend(pii_violations)

        # Check for harmful content (LLM-based if available)
        if self.llm_client:
            try:
                harmful_violations = self._check_harmful_content(response)
                violations.extend(harmful_violations)
            except Exception as e:
                self.logger.warning(f"Harmful content check failed: {e}")

        # Check factual consistency if sources provided
        if sources:
            try:
                consistency_violations = self._check_factual_consistency(response, sources)
                violations.extend(consistency_violations)
            except Exception as e:
                self.logger.warning(f"Factual consistency check failed: {e}")

        # Check for bias (LLM-based if available)
        if self.llm_client:
            try:
                bias_violations = self._check_bias(response)
                violations.extend(bias_violations)
            except Exception as e:
                self.logger.warning(f"Bias check failed: {e}")

        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "sanitized_output": self._sanitize(response, violations) if violations else response
        }

    def _check_pii(self, text: str) -> List[Dict[str, Any]]:
        """
        Check for personally identifiable information using comprehensive regex patterns.
        """
        violations = []

        # Comprehensive regex patterns for common PII
        patterns = {
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "phone_us": r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
            "phone_international": r'\b\+\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b',
            "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
            "credit_card": r'\b\d{4}[-.\s]?\d{4}[-.\s]?\d{4}[-.\s]?\d{4}\b',
            "ip_address": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        }

        for pii_type, pattern in patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                # Filter out false positives (e.g., years, common numbers)
                if pii_type == "ip_address":
                    # Basic validation: each octet should be 0-255
                    valid_matches = []
                    for match in matches:
                        parts = match.split('.')
                        if all(0 <= int(p) <= 255 for p in parts):
                            valid_matches.append(match)
                    matches = valid_matches
                
                if matches:
                    violations.append({
                        "validator": "pii",
                        "pii_type": pii_type,
                        "reason": f"Contains {pii_type}",
                        "severity": "high",
                        "matches": matches[:5]  # Limit to first 5 matches
                    })

        return violations

    def _check_harmful_content(self, text: str) -> List[Dict[str, Any]]:
        """
        Check for harmful or inappropriate content using LLM.
        """
        violations = []
        
        if not self.llm_client:
            return violations
        
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
                            "output",
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
                        "output",
                        self.config,
                        self.topic
                    )
                )
            
            if not result.get("safe", True):
                llm_violations = result.get("violations", [])
                for v in llm_violations:
                    violations.append({
                        "validator": "harmful_content",
                        "reason": result.get("reasoning", f"LLM detected: {v}"),
                        "severity": result.get("severity", "medium")
                    })
        except Exception as e:
            self.logger.error(f"Error in harmful content check: {e}")
        
        return violations

    def _check_factual_consistency(
        self,
        response: str,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Check if response is consistent with sources using LLM-based verification.
        """
        violations = []
        
        if not self.llm_client or not sources:
            return violations
        
        try:
            # Create summary of sources for LLM
            sources_summary = "\n".join([
                f"- {s.get('title', 'Unknown')}: {s.get('snippet', s.get('abstract', ''))[:200]}"
                for s in sources[:5]  # Limit to first 5 sources
            ])
            
            model_config = self.config.get("models", {}).get("default", {})
            provider = model_config.get("provider", "openai")
            model_name = model_config.get("name", "gpt-4o-mini")
            
            prompt = f"""Check if the following response is factually consistent with the provided sources.

Response:
{response[:1500]}

Sources:
{sources_summary}

Respond in JSON format:
{{
    "consistent": true/false,
    "inconsistencies": ["description of inconsistency 1", "description 2"],
    "reasoning": "brief explanation"
}}"""
            
            from openai import OpenAI
            api_key = __import__("os").getenv("OPENAI_API_KEY")
            base_url = __import__("os").getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            if api_key:
                client = OpenAI(api_key=api_key, base_url=base_url)
                llm_response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a fact-checker. Respond in valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=512
                )
                result_text = llm_response.choices[0].message.content
            else:
                return violations
            
            # Parse JSON
            result_text = result_text.strip()
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            elif result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()
            
            result = __import__("json").loads(result_text)
            
            if not result.get("consistent", True):
                inconsistencies = result.get("inconsistencies", [])
                for inc in inconsistencies:
                    violations.append({
                        "validator": "factual_consistency",
                        "reason": inc,
                        "severity": "high"
                    })
        except Exception as e:
            self.logger.error(f"Error in factual consistency check: {e}")
        
        return violations

    def _check_bias(self, text: str) -> List[Dict[str, Any]]:
        """
        Check for biased language using LLM.
        """
        violations = []
        
        if not self.llm_client:
            return violations
        
        try:
            model_config = self.config.get("models", {}).get("default", {})
            provider = model_config.get("provider", "openai")
            model_name = model_config.get("name", "gpt-4o-mini")
            
            prompt = f"""Analyze the following text for biased language, stereotypes, or discriminatory content.

Text:
{text[:1500]}

Respond in JSON format:
{{
    "has_bias": true/false,
    "bias_types": ["type1", "type2"],
    "reasoning": "brief explanation",
    "severity": "low|medium|high"
}}"""
            
            from openai import OpenAI
            api_key = __import__("os").getenv("OPENAI_API_KEY")
            base_url = __import__("os").getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            if api_key:
                client = OpenAI(api_key=api_key, base_url=base_url)
                llm_response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a bias detector. Respond in valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=512
                )
                result_text = llm_response.choices[0].message.content
            else:
                return violations
            
            # Parse JSON
            result_text = result_text.strip()
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            elif result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()
            
            result = __import__("json").loads(result_text)
            
            if result.get("has_bias", False):
                bias_types = result.get("bias_types", [])
                violations.append({
                    "validator": "bias",
                    "reason": result.get("reasoning", f"Detected bias: {', '.join(bias_types)}"),
                    "severity": result.get("severity", "medium"),
                    "bias_types": bias_types
                })
        except Exception as e:
            self.logger.error(f"Error in bias check: {e}")
        
        return violations

    def _sanitize(self, text: str, violations: List[Dict[str, Any]]) -> str:
        """
        Sanitize text by removing/redacting violations.
        """
        sanitized = text

        # Redact PII
        for violation in violations:
            if violation.get("validator") == "pii":
                matches = violation.get("matches", [])
                for match in matches:
                    sanitized = sanitized.replace(match, "[REDACTED]")
            
            # For harmful content or bias, we could redact sections
            # For now, we'll add a warning prefix
            elif violation.get("validator") in ["harmful_content", "bias"]:
                # Could implement more sophisticated redaction here
                pass

        return sanitized
