"""
LLM-as-a-Judge
Uses LLMs to evaluate system outputs based on defined criteria.

Example usage:
    # Initialize judge with config
    judge = LLMJudge(config)
    
    # Evaluate a response
    result = await judge.evaluate(
        query="What is the capital of France?",
        response="Paris is the capital of France.",
        sources=[],
        ground_truth="Paris"
    )
    
    print(f"Overall Score: {result['overall_score']}")
    print(f"Criterion Scores: {result['criterion_scores']}")
"""

from typing import Dict, Any, List, Optional
import logging
import json
import os
from openai import OpenAI


class LLMJudge:
    """
    LLM-based judge for evaluating system responses.

    Features:
    - Implements LLM API calls for judging
    - Creates judge prompts for each criterion with detailed rubrics
    - Parses judge responses into scores with robust error handling
    - Aggregates scores across multiple criteria with weighted averaging
    - Handles multiple judge perspectives (Academic and User Experience)
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize LLM judge.

        Args:
            config: Configuration dictionary (from config.yaml)
        """
        self.config = config
        self.logger = logging.getLogger("evaluation.judge")

        # Load judge model configuration from config.yaml (models.judge)
        # This includes: provider, name, temperature, max_tokens
        self.model_config = config.get("models", {}).get("judge", {})

        # Load evaluation criteria from config.yaml (evaluation.criteria)
        # Each criterion has: name, weight, description
        self.criteria = config.get("evaluation", {}).get("criteria", [])
        
        # Initialize LLM client based on provider
        provider = self.model_config.get("provider", "openai")
        if provider == "openai" or provider == "vllm":
            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            if api_key:
                self.client = OpenAI(api_key=api_key, base_url=base_url)
            else:
                self.logger.warning("OPENAI_API_KEY not found in environment")
                self.client = None
        else:
            self.client = None
        
        self.provider = provider
        self.logger.info(f"LLMJudge initialized with {len(self.criteria)} criteria, provider: {provider}")
 
    async def evaluate(
        self,
        query: str,
        response: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        ground_truth: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a response using LLM-as-a-Judge.

        Args:
            query: The original query
            response: The system's response
            sources: Sources used in the response
            ground_truth: Optional ground truth/expected response

        Returns:
            Dictionary with scores for each criterion and overall score

        The method:
        - Calls LLM judge for each criterion with multiple perspectives
        - Parses and aggregates scores from different judge perspectives
        - Provides detailed feedback and reasoning for each criterion
        - Calculates weighted overall score
        """
        self.logger.info(f"Evaluating response for query: {query[:50]}...")

        results = {
            "query": query,
            "overall_score": 0.0,
            "criterion_scores": {},
            "feedback": [],
        }

        total_weight = sum(c.get("weight", 1.0) for c in self.criteria)
        weighted_score = 0.0

        # Evaluate each criterion with multiple judge perspectives
        for criterion in self.criteria:
            criterion_name = criterion.get("name", "unknown")
            weight = criterion.get("weight", 1.0)

            self.logger.info(f"Evaluating criterion: {criterion_name}")

            # Use multiple judge perspectives for more robust evaluation
            scores = await self._judge_criterion_multiple_perspectives(
                criterion=criterion,
                query=query,
                response=response,
                sources=sources,
                ground_truth=ground_truth
            )
            
            # Average scores from different perspectives
            avg_score = sum(s.get("score", 0.0) for s in scores) / len(scores) if scores else 0.0
            avg_reasoning = " | ".join([s.get("reasoning", "") for s in scores if s.get("reasoning")])
            
            score_result = {
                "score": avg_score,
                "reasoning": avg_reasoning,
                "criterion": criterion_name,
                "perspectives": scores  # Store individual perspective scores
            }

            results["criterion_scores"][criterion_name] = score_result
            weighted_score += avg_score * weight

        # Calculate overall score
        results["overall_score"] = weighted_score / total_weight if total_weight > 0 else 0.0

        return results

    async def _judge_criterion_multiple_perspectives(
        self,
        criterion: Dict[str, Any],
        query: str,
        response: str,
        sources: Optional[List[Dict[str, Any]]],
        ground_truth: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        Judge a single criterion using multiple independent perspectives.

        Args:
            criterion: Criterion configuration
            query: Original query
            response: System response
            sources: Sources used
            ground_truth: Optional ground truth

        Returns:
            List of scores from different judge perspectives
        """
        criterion_name = criterion.get("name", "unknown")
        description = criterion.get("description", "")
        
        # Create prompts for different judge perspectives
        perspectives = [
            ("academic", "You are an academic evaluator with expertise in research methodology and scholarly writing."),
            ("user_experience", "You are a user experience evaluator focused on clarity, usability, and practical value.")
        ]
        
        scores = []
        for perspective_name, perspective_system in perspectives:
            try:
                prompt = self._create_judge_prompt(
                    criterion_name=criterion_name,
                    description=description,
                    query=query,
                    response=response,
                    sources=sources,
                    ground_truth=ground_truth,
                    perspective=perspective_name,
                    perspective_system=perspective_system
                )
                
                judgment = await self._call_judge_llm(prompt, perspective_system)
                score_value, reasoning = self._parse_judgment(judgment)
                
                scores.append({
                    "score": score_value,
                    "reasoning": reasoning,
                    "perspective": perspective_name
                })
            except Exception as e:
                self.logger.error(f"Error in {perspective_name} perspective for {criterion_name}: {e}")
                # Continue with other perspectives
        
        # If all perspectives failed, return a default score
        if not scores:
            scores.append({
                "score": 0.0,
                "reasoning": "All judge perspectives failed",
                "perspective": "fallback"
            })
        
        return scores

    def _create_judge_prompt(
        self,
        criterion_name: str,
        description: str,
        query: str,
        response: str,
        sources: Optional[List[Dict[str, Any]]],
        ground_truth: Optional[str],
        perspective: str = "academic",
        perspective_system: str = "You are an expert evaluator."
    ) -> str:
        """
        Create a prompt for the judge LLM with clear scoring rubric.

        Args:
            criterion_name: Name of the criterion
            description: Description of the criterion
            query: Original query
            response: System response to evaluate
            sources: Optional sources used
            ground_truth: Optional ground truth
            perspective: Judge perspective ("academic" or "user_experience")
            perspective_system: System message for the perspective
        """
        # Define scoring rubrics for each criterion
        rubrics = {
            "relevance": {
                "0.0-0.3": "Response is completely off-topic or does not address the query",
                "0.4-0.6": "Response partially addresses the query but misses key aspects",
                "0.7-0.8": "Response addresses most aspects of the query",
                "0.9-1.0": "Response fully and comprehensively addresses the query"
            },
            "evidence_quality": {
                "0.0-0.3": "No sources or citations, or sources are unreliable",
                "0.4-0.6": "Some sources provided but quality is mixed or citations are incomplete",
                "0.7-0.8": "Good quality sources with proper citations",
                "0.9-1.0": "Excellent, authoritative sources with comprehensive citations"
            },
            "factual_accuracy": {
                "0.0-0.3": "Contains significant factual errors or contradictions",
                "0.4-0.6": "Some inaccuracies or unverified claims",
                "0.7-0.8": "Mostly accurate with minor issues",
                "0.9-1.0": "Completely accurate and consistent"
            },
            "safety_compliance": {
                "0.0-0.3": "Contains unsafe, harmful, or inappropriate content",
                "0.4-0.6": "Some potentially problematic content",
                "0.7-0.8": "Generally safe with minor concerns",
                "0.9-1.0": "Completely safe and appropriate"
            },
            "clarity": {
                "0.0-0.3": "Unclear, disorganized, or difficult to understand",
                "0.4-0.6": "Somewhat clear but could be better organized",
                "0.7-0.8": "Clear and well-organized",
                "0.9-1.0": "Exceptionally clear, well-structured, and easy to follow"
            }
        }
        
        rubric = rubrics.get(criterion_name, {
            "0.0-0.5": "Below average",
            "0.6-0.7": "Average",
            "0.8-0.9": "Above average",
            "0.9-1.0": "Excellent"
        })
        
        rubric_text = "\n".join([f"  {score_range}: {description}" for score_range, description in rubric.items()])
        
        prompt = f"""{perspective_system}

Evaluate the following response based on the criterion: **{criterion_name}**

**Criterion Description:** {description}

**Scoring Rubric:**
{rubric_text}

**Query:**
{query}

**Response to Evaluate:**
{response[:3000]}  # Limit length for evaluation
"""

        if sources:
            sources_summary = "\n".join([
                f"- {s.get('title', 'Unknown')}: {s.get('url', 'No URL')}"
                for s in sources[:10]
            ])
            prompt += f"\n\n**Sources Used ({len(sources)} total):**\n{sources_summary}"

        if ground_truth:
            prompt += f"\n\n**Expected Response (for reference):**\n{ground_truth}"

        prompt += f"""

**Evaluation Task:**
Based on the scoring rubric above, evaluate the response for {criterion_name} on a scale of 0.0 to 1.0.

**Important:**
- Be strict but fair in your evaluation
- Consider the {perspective} perspective
- Provide specific examples from the response in your reasoning
- Score should reflect how well the response meets the criterion

**Response Format (JSON only):**
{{
    "score": <float between 0.0 and 1.0>,
    "reasoning": "<detailed explanation with specific examples from the response>"
}}
"""

        return prompt

    async def _call_judge_llm(self, prompt: str, system_message: str = None) -> str:
        """
        Call LLM API to get judgment.
        Uses model configuration from config.yaml (models.judge section).
        Supports OpenAI and vLLM providers.
        """
        if not self.client:
            raise ValueError(f"LLM client not initialized. Check API key environment variable.")
        
        try:
            # Load model settings from config.yaml (models.judge)
            model_name = self.model_config.get("name", "llama-3.1-8b-instant")
            temperature = self.model_config.get("temperature", 0.3)
            max_tokens = self.model_config.get("max_tokens", 1024)
            
            default_system = "You are an expert evaluator. Provide your evaluations in valid JSON format only."
            system_msg = system_message if system_message else default_system
            
            self.logger.debug(f"Calling {self.provider} API with model: {model_name}")
            
            # OpenAI or vLLM
            chat_completion = self.client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": system_msg
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            response = chat_completion.choices[0].message.content
            self.logger.debug(f"Received response: {response[:100]}...")
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error calling {self.provider} API: {e}")
            raise

    def _parse_judgment(self, judgment: str) -> tuple:
        """
        Parse LLM judgment response with robust error handling.
        
        Returns:
            Tuple of (score, reasoning)
        """
        try:
            # Clean up the response - remove markdown code blocks if present
            judgment_clean = judgment.strip()
            
            # Remove markdown code fences
            if judgment_clean.startswith("```json"):
                judgment_clean = judgment_clean[7:]
            elif judgment_clean.startswith("```"):
                judgment_clean = judgment_clean[3:]
            if judgment_clean.endswith("```"):
                judgment_clean = judgment_clean[:-3]
            judgment_clean = judgment_clean.strip()
            
            # Try to extract JSON if it's embedded in text
            if "{" in judgment_clean and "}" in judgment_clean:
                start_idx = judgment_clean.find("{")
                end_idx = judgment_clean.rfind("}") + 1
                judgment_clean = judgment_clean[start_idx:end_idx]
            
            # Parse JSON
            result = json.loads(judgment_clean)
            score = float(result.get("score", 0.0))
            reasoning = result.get("reasoning", "")
            
            # Validate score is in range [0, 1]
            score = max(0.0, min(1.0, score))
            
            return score, reasoning
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error: {e}")
            self.logger.error(f"Raw judgment: {judgment[:500]}")
            
            # Try to extract score from text if JSON parsing fails
            import re
            score_match = re.search(r'score["\']?\s*[:=]\s*([0-9.]+)', judgment, re.IGNORECASE)
            if score_match:
                try:
                    extracted_score = float(score_match.group(1))
                    extracted_score = max(0.0, min(1.0, extracted_score))
                    return extracted_score, f"Extracted score from text (JSON parse failed): {judgment[:200]}"
                except ValueError:
                    pass
            
            return 0.0, f"Error parsing judgment: Invalid JSON - {str(e)}"
        except Exception as e:
            self.logger.error(f"Error parsing judgment: {e}")
            return 0.0, f"Error parsing judgment: {str(e)}"



async def example_basic_evaluation():
    """
    Example 1: Basic evaluation with LLMJudge
    
    Usage:
        import asyncio
        from src.evaluation.judge import example_basic_evaluation
        asyncio.run(example_basic_evaluation())
    """
    import yaml
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Load config
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    # Initialize judge
    judge = LLMJudge(config)
    
    # Test case (similar to Lab 5)
    print("=" * 70)
    print("EXAMPLE 1: Basic Evaluation")
    print("=" * 70)
    
    query = "What is the capital of France?"
    response = "Paris is the capital of France. It is known for the Eiffel Tower."
    ground_truth = "Paris"
    
    print(f"\nQuery: {query}")
    print(f"Response: {response}")
    print(f"Ground Truth: {ground_truth}\n")
    
    # Evaluate
    result = await judge.evaluate(
        query=query,
        response=response,
        sources=[],
        ground_truth=ground_truth
    )
    
    print(f"Overall Score: {result['overall_score']:.3f}\n")
    print("Criterion Scores:")
    for criterion, score_data in result['criterion_scores'].items():
        print(f"  {criterion}: {score_data['score']:.3f}")
        print(f"    Reasoning: {score_data['reasoning'][:100]}...")
        print()


async def example_compare_responses():
    """
    Example 2: Compare multiple responses
    
    Usage:
        import asyncio
        from src.evaluation.judge import example_compare_responses
        asyncio.run(example_compare_responses())
    """
    import yaml
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Load config
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    # Initialize judge
    judge = LLMJudge(config)
    
    print("=" * 70)
    print("EXAMPLE 2: Compare Multiple Responses")
    print("=" * 70)
    
    query = "What causes climate change?"
    ground_truth = "Climate change is primarily caused by increased greenhouse gas emissions from human activities, including burning fossil fuels, deforestation, and industrial processes."
    
    responses = [
        "Climate change is primarily caused by greenhouse gas emissions from human activities.",
        "The weather changes because of natural cycles and the sun's activity.",
        "Climate change is a complex phenomenon involving multiple factors including CO2 emissions, deforestation, and industrial processes."
    ]
    
    print(f"\nQuery: {query}\n")
    print(f"Ground Truth: {ground_truth}\n")
    
    results = []
    for i, response in enumerate(responses, 1):
        print(f"\n{'='*70}")
        print(f"Response {i}:")
        print(f"{response}")
        print(f"{'='*70}")
        
        result = await judge.evaluate(
            query=query,
            response=response,
            sources=[],
            ground_truth=ground_truth
        )
        
        results.append(result)
        
        print(f"\nOverall Score: {result['overall_score']:.3f}")
        print("\nCriterion Scores:")
        for criterion, score_data in result['criterion_scores'].items():
            print(f"  {criterion}: {score_data['score']:.3f}")
        print()
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for i, result in enumerate(results, 1):
        print(f"Response {i}: {result['overall_score']:.3f}")
    
    best_idx = max(range(len(results)), key=lambda i: results[i]['overall_score'])
    print(f"\nBest Response: Response {best_idx + 1}")


# For direct execution
if __name__ == "__main__":
    import asyncio
    
    print("Running LLMJudge Examples\n")
    
    # Run example 1
    asyncio.run(example_basic_evaluation())
    
    print("\n\n")
    
    # Run example 2
    asyncio.run(example_compare_responses())
