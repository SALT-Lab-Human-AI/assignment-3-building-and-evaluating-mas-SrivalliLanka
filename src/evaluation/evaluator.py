"""
System Evaluator
Runs batch evaluations and generates reports.

Example usage:
    # Load config
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    
    # Initialize evaluator with orchestrator
    evaluator = SystemEvaluator(config, orchestrator=my_orchestrator)
    
    # Run evaluation
    report = await evaluator.evaluate_system("data/test_queries.json")
    
    # Results are automatically saved to outputs/
"""

from typing import Dict, Any, List, Optional
import json
import logging
from pathlib import Path
from datetime import datetime
import asyncio

from .judge import LLMJudge


class SystemEvaluator:
    """
    Evaluates the multi-agent system using test queries and LLM-as-a-Judge.

    Features:
    - Loads test queries from JSON file
    - Runs system on all test queries
    - Collects and aggregates results
    - Generates comprehensive evaluation reports
    - Performs error analysis and performance metrics
    """

    def __init__(self, config: Dict[str, Any], orchestrator=None):
        """
        Initialize evaluator.

        Args:
            config: Configuration dictionary (from config.yaml)
            orchestrator: The orchestrator to evaluate
        """
        self.config = config
        self.orchestrator = orchestrator
        self.logger = logging.getLogger("evaluation.evaluator")

        # Load evaluation configuration from config.yaml
        eval_config = config.get("evaluation", {})
        self.enabled = eval_config.get("enabled", True)
        self.max_test_queries = eval_config.get("num_test_queries", None)
        
        # Initialize judge (passes config to load judge model settings and criteria)
        self.judge = LLMJudge(config)

        # Evaluation results
        self.results: List[Dict[str, Any]] = []
        
        self.logger.info(f"SystemEvaluator initialized (enabled={self.enabled})")

    async def evaluate_system(
        self,
        test_queries_path: str = "data/test_queries.json"
    ) -> Dict[str, Any]:
        """
        Run full system evaluation.

        Args:
            test_queries_path: Path to test queries JSON file

        Returns:
            Evaluation results and statistics

        The method:
        - Loads test queries from the specified file
        - Runs each query through the orchestrator
        - Evaluates each response using LLM-as-a-Judge
        - Aggregates results and generates comprehensive reports
        """
        # Check if evaluation is enabled in config.yaml
        if not self.enabled:
            self.logger.warning("Evaluation is disabled in config.yaml")
            return {"error": "Evaluation is disabled in configuration"}
        
        self.logger.info("Starting system evaluation")

        # Load test queries
        test_queries = self._load_test_queries(test_queries_path)
        self.logger.info(f"Loaded {len(test_queries)} test queries")

        # Evaluate each query
        for i, test_case in enumerate(test_queries, 1):
            self.logger.info(f"Evaluating query {i}/{len(test_queries)}")

            try:
                result = await self._evaluate_query(test_case)
                self.results.append(result)
            except Exception as e:
                self.logger.error(f"Error evaluating query {i}: {e}")
                self.results.append({
                    "query": test_case.get("query", ""),
                    "error": str(e)
                })

        # Aggregate results
        report = self._generate_report()

        # Save results
        self._save_results(report)

        return report

    async def _evaluate_query(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate a single test query.

        Args:
            test_case: Test case with query and optional ground truth

        Returns:
            Evaluation result for this query

        This shows how to integrate with the orchestrator.
        """
        query = test_case.get("query", "")
        ground_truth = test_case.get("ground_truth")
        expected_sources = test_case.get("expected_sources", [])
        category = test_case.get("category", "unknown")  # Extract category from test case

        # Run through orchestrator if available
        if self.orchestrator:
            try:
                # Call orchestrator's process_query method (synchronous wrapper)
                # Use reduced max_rounds (2) for efficient 6-query evaluation
                # The orchestrator handles async internally
                response_data = self.orchestrator.process_query(query, max_rounds=2)
                
                # Extract sources from conversation history if available
                sources = []
                conversation_history = response_data.get("conversation_history", [])
                for msg in conversation_history:
                    content = msg.get("content", "")
                    # Handle content that might be a list
                    if isinstance(content, list):
                        content = " ".join(str(item) for item in content)
                    elif not isinstance(content, str):
                        content = str(content)
                    # Extract URLs from messages
                    import re
                    urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', content)
                    sources.extend([{"url": url} for url in urls])
                
                # Add sources to metadata
                if sources:
                    metadata = response_data.get("metadata", {})
                    metadata["sources"] = sources[:20]  # Limit to 20 sources
                    response_data["metadata"] = metadata
                
                # Check for errors in response
                response_text = response_data.get("response", "")
                has_error = (
                    "error" in response_data or
                    response_data.get("metadata", {}).get("error", False) or
                    response_text.startswith("Error:") or
                    "An error occurred" in response_text or
                    "timed out" in response_text.lower() or
                    "bound to a different event loop" in response_text.lower()
                )
                
                if has_error:
                    error_msg = response_data.get("error", response_text)
                    self.logger.warning(f"Query returned error: {error_msg[:100]}")
                    return {
                        "query": query,
                        "response": response_text,
                        "error": error_msg,
                        "category": category,
                        "metadata": response_data.get("metadata", {}),
                        "ground_truth": ground_truth
                    }
                
            except Exception as e:
                self.logger.error(f"Error processing query through orchestrator: {e}", exc_info=True)
                response_data = {
                    "query": query,
                    "response": f"Error: {str(e)}",
                    "citations": [],
                    "metadata": {"error": str(e), "sources": []}
                }
                return {
                    "query": query,
                    "response": f"Error: {str(e)}",
                    "error": str(e),
                    "category": category,
                    "metadata": {"error": str(e), "sources": []},
                    "ground_truth": ground_truth
                }
        else:
            # Placeholder for testing without orchestrator
            self.logger.warning("No orchestrator provided, using placeholder response")
            response_data = {
                "query": query,
                "response": "Placeholder response - orchestrator not connected",
                "citations": [],
                "metadata": {"num_sources": 0}
            }

        # Evaluate response using LLM-as-a-Judge
        evaluation = await self.judge.evaluate(
            query=query,
            response=response_data.get("response", ""),
            sources=response_data.get("metadata", {}).get("sources", []),
            ground_truth=ground_truth
        )

        # Clean metadata to remove non-serializable objects and limit size
        metadata = response_data.get("metadata", {})
        # Remove conversation_history from metadata if present (it can cause context length issues)
        # Keep only essential metadata
        cleaned_metadata = {
            "num_messages": metadata.get("num_messages", 0),
            "num_sources": metadata.get("num_sources", 0),
            "agents_involved": metadata.get("agents_involved", []),
        }
        # Only include error info if present
        if "error" in metadata:
            cleaned_metadata["error"] = metadata.get("error")
        if "error_type" in metadata:
            cleaned_metadata["error_type"] = metadata.get("error_type")
        
        return {
            "query": query,
            "response": response_data.get("response", ""),
            "evaluation": evaluation,
            "category": category,  # Include category in result
            "metadata": cleaned_metadata,
            "ground_truth": ground_truth
        }

    def _clean_for_json(self, obj: Any) -> Any:
        """
        Recursively clean object for JSON serialization.
        Removes non-serializable objects like FunctionCall.
        """
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                # Skip private attributes
                if k.startswith('_'):
                    continue
                try:
                    cleaned[k] = self._clean_for_json(v)
                except (TypeError, ValueError):
                    # If cleaning fails, convert to string
                    cleaned[k] = str(v)
            return cleaned
        elif isinstance(obj, list):
            return [self._clean_for_json(item) for item in obj]
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        elif hasattr(obj, '__dict__'):
            # For objects, try to convert to dict
            try:
                return self._clean_for_json(obj.__dict__)
            except (TypeError, ValueError):
                return str(obj)
        else:
            # For other types, convert to string
            return str(obj)

    def _load_test_queries(self, path: str) -> List[Dict[str, Any]]:
        """
        Load test queries from JSON file.

        The method loads queries from the specified JSON file and validates them.
        Queries can be limited by num_test_queries configuration.
        """
        path_obj = Path(path)
        if not path_obj.exists():
            self.logger.warning(f"Test queries file not found: {path}")
            return []

        with open(path_obj, 'r') as f:
            queries = json.load(f)

        # Limit number of queries if configured in config.yaml
        if self.max_test_queries and len(queries) > self.max_test_queries:
            self.logger.info(f"Limiting to {self.max_test_queries} queries (from config.yaml)")
            queries = queries[:self.max_test_queries]

        return queries

    def _generate_report(self) -> Dict[str, Any]:
        """
        Generate evaluation report with statistics, error analysis, and performance metrics.
        """
        if not self.results:
            return {"error": "No results to report"}

        # Calculate statistics
        total_queries = len(self.results)
        successful = [r for r in self.results if "error" not in r]
        failed = [r for r in self.results if "error" in r]

        # Aggregate scores
        criterion_scores = {}
        overall_scores = []
        category_scores = {}  # Performance by query category

        for result in successful:
            evaluation = result.get("evaluation", {})
            overall_score = evaluation.get("overall_score", 0.0)
            overall_scores.append(overall_score)

            # Collect scores by criterion
            for criterion, score_data in evaluation.get("criterion_scores", {}).items():
                if criterion not in criterion_scores:
                    criterion_scores[criterion] = []
                # Handle both dict and float scores
                score_value = score_data.get("score", 0.0) if isinstance(score_data, dict) else score_data
                criterion_scores[criterion].append(score_value)
            
            # Group by category if available
            category = result.get("category", "unknown")
            if category not in category_scores:
                category_scores[category] = []
            category_scores[category].append(overall_score)

        # Calculate averages
        avg_overall = sum(overall_scores) / len(overall_scores) if overall_scores else 0.0

        avg_criterion_scores = {}
        for criterion, scores in criterion_scores.items():
            avg_criterion_scores[criterion] = sum(scores) / len(scores) if scores else 0.0
        
        # Calculate category averages
        avg_category_scores = {}
        for category, scores in category_scores.items():
            avg_category_scores[category] = sum(scores) / len(scores) if scores else 0.0

        # Find best and worst
        best_result = max(successful, key=lambda r: r.get("evaluation", {}).get("overall_score", 0.0)) if successful else None
        worst_result = min(successful, key=lambda r: r.get("evaluation", {}).get("overall_score", 0.0)) if successful else None

        # Error analysis
        error_analysis = self._analyze_errors(failed)
        
        # Performance analysis
        performance_analysis = self._analyze_performance(successful)

        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_queries": total_queries,
                "successful": len(successful),
                "failed": len(failed),
                "success_rate": len(successful) / total_queries if total_queries > 0 else 0.0
            },
            "scores": {
                "overall_average": avg_overall,
                "by_criterion": avg_criterion_scores,
                "by_category": avg_category_scores
            },
            "best_result": {
                "query": best_result.get("query", "") if best_result else "",
                "score": best_result.get("evaluation", {}).get("overall_score", 0.0) if best_result else 0.0,
                "category": best_result.get("category", "unknown") if best_result else None
            } if best_result else None,
            "worst_result": {
                "query": worst_result.get("query", "") if worst_result else "",
                "score": worst_result.get("evaluation", {}).get("overall_score", 0.0) if worst_result else 0.0,
                "category": worst_result.get("category", "unknown") if worst_result else None
            } if worst_result else None,
            "error_analysis": error_analysis,
            "performance_analysis": performance_analysis,
            "detailed_results": self.results
        }

        return report
    
    def _analyze_errors(self, failed: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze error patterns in failed queries."""
        if not failed:
            return {"total_errors": 0, "error_types": {}}
        
        error_types = {}
        error_messages = []
        
        for result in failed:
            error = result.get("error", "Unknown error")
            error_messages.append(error)
            
            # Categorize errors
            error_category = "unknown"
            if "timeout" in str(error).lower():
                error_category = "timeout"
            elif "api" in str(error).lower() or "key" in str(error).lower():
                error_category = "api_error"
            elif "network" in str(error).lower() or "connection" in str(error).lower():
                error_category = "network_error"
            elif "validation" in str(error).lower() or "parse" in str(error).lower():
                error_category = "validation_error"
            else:
                error_category = "other"
            
            error_types[error_category] = error_types.get(error_category, 0) + 1
        
        return {
            "total_errors": len(failed),
            "error_types": error_types,
            "sample_errors": error_messages[:5]  # First 5 errors
        }
    
    def _analyze_performance(self, successful: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze performance patterns."""
        if not successful:
            return {}
        
        # Score distribution
        scores = [r.get("evaluation", {}).get("overall_score", 0.0) for r in successful]
        score_ranges = {
            "excellent (0.9-1.0)": sum(1 for s in scores if 0.9 <= s <= 1.0),
            "good (0.7-0.89)": sum(1 for s in scores if 0.7 <= s < 0.9),
            "fair (0.5-0.69)": sum(1 for s in scores if 0.5 <= s < 0.7),
            "poor (0.0-0.49)": sum(1 for s in scores if 0.0 <= s < 0.5)
        }
        
        # Weakest criterion (lowest average score)
        criterion_averages = {}
        for result in successful:
            evaluation = result.get("evaluation", {})
            for criterion, score_data in evaluation.get("criterion_scores", {}).items():
                if criterion not in criterion_averages:
                    criterion_averages[criterion] = []
                score_value = score_data.get("score", 0.0) if isinstance(score_data, dict) else score_data
                criterion_averages[criterion].append(score_value)
        
        avg_by_criterion = {
            criterion: sum(scores) / len(scores) 
            for criterion, scores in criterion_averages.items()
            if scores
        }
        
        weakest_criterion = min(avg_by_criterion.items(), key=lambda x: x[1]) if avg_by_criterion else None
        
        return {
            "score_distribution": score_ranges,
            "weakest_criterion": {
                "name": weakest_criterion[0],
                "average_score": weakest_criterion[1]
            } if weakest_criterion else None,
            "total_successful": len(successful)
        }

    def _save_results(self, report: Dict[str, Any]):
        """
        Save evaluation results to file with comprehensive reports.
        """
        output_dir = Path("outputs")
        output_dir.mkdir(exist_ok=True)

        # Save detailed results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = output_dir / f"evaluation_{timestamp}.json"

        # Helper function to handle non-JSON-serializable objects
        def _json_default(obj):
            """Default JSON serializer for objects not serializable by default json code."""
            from datetime import datetime, date
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if hasattr(obj, '__dict__'):
                return obj.__dict__
            if hasattr(obj, '__str__'):
                return str(obj)
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

        # Clean the report to remove non-serializable objects
        cleaned_report = self._clean_for_json(report)

        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_report, f, indent=2, default=_json_default, ensure_ascii=False)

        self.logger.info(f"Evaluation results saved to {results_file}")

        # Save comprehensive summary
        summary_file = output_dir / f"evaluation_summary_{timestamp}.txt"
        with open(summary_file, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("EVALUATION SUMMARY\n")
            f.write("=" * 70 + "\n\n")

            summary = report.get("summary", {})
            f.write("OVERVIEW\n")
            f.write("-" * 70 + "\n")
            f.write(f"Total Queries: {summary.get('total_queries', 0)}\n")
            f.write(f"Successful: {summary.get('successful', 0)}\n")
            f.write(f"Failed: {summary.get('failed', 0)}\n")
            f.write(f"Success Rate: {summary.get('success_rate', 0.0):.2%}\n\n")

            scores = report.get("scores", {})
            f.write("SCORES\n")
            f.write("-" * 70 + "\n")
            f.write(f"Overall Average Score: {scores.get('overall_average', 0.0):.3f}\n\n")

            f.write("Scores by Criterion:\n")
            for criterion, score in scores.get("by_criterion", {}).items():
                f.write(f"  {criterion}: {score:.3f}\n")
            
            f.write("\nScores by Category:\n")
            for category, score in scores.get("by_category", {}).items():
                f.write(f"  {category}: {score:.3f}\n")
            
            f.write("\n" + "=" * 70 + "\n")
            f.write("BEST AND WORST PERFORMING QUERIES\n")
            f.write("=" * 70 + "\n\n")
            
            best = report.get("best_result")
            if best:
                f.write(f"BEST:\n")
                f.write(f"  Query: {best.get('query', '')}\n")
                f.write(f"  Score: {best.get('score', 0.0):.3f}\n")
                f.write(f"  Category: {best.get('category', 'unknown')}\n\n")
            
            worst = report.get("worst_result")
            if worst:
                f.write(f"WORST:\n")
                f.write(f"  Query: {worst.get('query', '')}\n")
                f.write(f"  Score: {worst.get('score', 0.0):.3f}\n")
                f.write(f"  Category: {worst.get('category', 'unknown')}\n\n")
            
            # Error analysis
            error_analysis = report.get("error_analysis", {})
            if error_analysis.get("total_errors", 0) > 0:
                f.write("=" * 70 + "\n")
                f.write("ERROR ANALYSIS\n")
                f.write("=" * 70 + "\n\n")
                f.write(f"Total Errors: {error_analysis.get('total_errors', 0)}\n")
                f.write("Error Types:\n")
                for error_type, count in error_analysis.get("error_types", {}).items():
                    f.write(f"  {error_type}: {count}\n")
                f.write("\nSample Errors:\n")
                for error in error_analysis.get("sample_errors", [])[:3]:
                    f.write(f"  - {error[:100]}\n")
                f.write("\n")
            
            # Performance analysis
            perf_analysis = report.get("performance_analysis", {})
            if perf_analysis:
                f.write("=" * 70 + "\n")
                f.write("PERFORMANCE ANALYSIS\n")
                f.write("=" * 70 + "\n\n")
                f.write("Score Distribution:\n")
                for range_name, count in perf_analysis.get("score_distribution", {}).items():
                    f.write(f"  {range_name}: {count}\n")
                
                weakest = perf_analysis.get("weakest_criterion")
                if weakest:
                    f.write(f"\nWeakest Criterion: {weakest.get('name')} (avg: {weakest.get('average_score', 0.0):.3f})\n")
                f.write("\n")

        self.logger.info(f"Summary saved to {summary_file}")
        
        # Save a markdown version for easier reading
        markdown_file = output_dir / f"evaluation_report_{timestamp}.md"
        self._save_markdown_report(report, markdown_file)
        self.logger.info(f"Markdown report saved to {markdown_file}")
    
    def _save_markdown_report(self, report: Dict[str, Any], filepath: Path):
        """Save evaluation report in Markdown format."""
        with open(filepath, 'w') as f:
            f.write("# Evaluation Report\n\n")
            f.write(f"**Date:** {report.get('timestamp', 'Unknown')}\n\n")
            
            summary = report.get("summary", {})
            f.write("## Overview\n\n")
            f.write(f"- **Total Queries:** {summary.get('total_queries', 0)}\n")
            f.write(f"- **Successful:** {summary.get('successful', 0)}\n")
            f.write(f"- **Failed:** {summary.get('failed', 0)}\n")
            f.write(f"- **Success Rate:** {summary.get('success_rate', 0.0):.2%}\n\n")
            
            scores = report.get("scores", {})
            f.write("## Scores\n\n")
            f.write(f"**Overall Average:** {scores.get('overall_average', 0.0):.3f}\n\n")
            
            f.write("### By Criterion\n\n")
            for criterion, score in scores.get("by_criterion", {}).items():
                f.write(f"- **{criterion}:** {score:.3f}\n")
            
            f.write("\n### By Category\n\n")
            for category, score in scores.get("by_category", {}).items():
                f.write(f"- **{category}:** {score:.3f}\n")
            
            f.write("\n## Best and Worst Queries\n\n")
            best = report.get("best_result")
            if best:
                f.write(f"### Best\n- Query: {best.get('query', '')}\n- Score: {best.get('score', 0.0):.3f}\n\n")
            
            worst = report.get("worst_result")
            if worst:
                f.write(f"### Worst\n- Query: {worst.get('query', '')}\n- Score: {worst.get('score', 0.0):.3f}\n\n")

    def export_for_report(self, output_path: str = "outputs/report_data.json"):
        """
        Export data formatted for inclusion in technical report.

        """
        if not self.results:
            self.logger.warning("No results to export")
            return
        
        # Create output directory
        output_dir = Path(output_path).parent
        output_dir.mkdir(exist_ok=True)
        
        # Format data for report
        report_data = {
            "evaluation_date": datetime.now().isoformat(),
            "total_queries": len(self.results),
            "results": self.results
        }
        
        # Clean the report data to remove non-serializable objects
        cleaned_data = self._clean_for_json(report_data)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Report data exported to {output_path}")


async def example_simple_evaluation():
    """
    Example 1: Simple evaluation without orchestrator
    Tests the evaluation pipeline with mock responses
    
    Usage:
        import asyncio
        from src.evaluation.evaluator import example_simple_evaluation
        asyncio.run(example_simple_evaluation())
    """
    import yaml
    from dotenv import load_dotenv
    
    load_dotenv()
    
    print("=" * 70)
    print("EXAMPLE 1: Simple Evaluation (No Orchestrator)")
    print("=" * 70)
    
    # Load config
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    # Create test queries in memory (no file needed)
    test_queries = [
        {
            "query": "What is the capital of France?",
            "ground_truth": "Paris is the capital of France."
        },
        {
            "query": "What are the benefits of exercise?",
            "ground_truth": "Exercise improves physical health, mental wellbeing, and reduces disease risk."
        }
    ]
    
    # Save test queries temporarily
    test_file = Path("data/test_queries_example.json")
    test_file.parent.mkdir(exist_ok=True)
    with open(test_file, 'w') as f:
        json.dump(test_queries, f, indent=2)
    
    # Initialize evaluator without orchestrator
    evaluator = SystemEvaluator(config, orchestrator=None)
    
    print("\nRunning evaluation on test queries...")
    print("Note: Using placeholder responses since no orchestrator is connected\n")
    
    # Run evaluation
    report = await evaluator.evaluate_system(str(test_file))
    
    # Display results
    print("\n" + "=" * 70)
    print("EVALUATION RESULTS")
    print("=" * 70)
    print(f"\nTotal Queries: {report['summary']['total_queries']}")
    print(f"Successful: {report['summary']['successful']}")
    print(f"Failed: {report['summary']['failed']}")
    print(f"Overall Average Score: {report['scores']['overall_average']:.3f}\n")
    
    print("Scores by Criterion:")
    for criterion, score in report['scores']['by_criterion'].items():
        print(f"  {criterion}: {score:.3f}")
    
    print(f"\nDetailed results saved to outputs/")
    
    # Clean up
    test_file.unlink()


async def example_with_orchestrator():
    """
    Example 2: Evaluation with orchestrator
    Shows how to connect the evaluator to your multi-agent system
    
    Usage:
        import asyncio
        from src.evaluation.evaluator import example_with_orchestrator
        asyncio.run(example_with_orchestrator())
    """
    import yaml
    from dotenv import load_dotenv
    
    load_dotenv()
    
    print("=" * 70)
    print("EXAMPLE 2: Evaluation with Orchestrator")
    print("=" * 70)
    
    # Load config
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    # Initialize orchestrator
    # Uses AutoGenOrchestrator for multi-agent coordination
    try:
        from src.autogen_orchestrator import AutoGenOrchestrator
        orchestrator = AutoGenOrchestrator(config)
        print("\nOrchestrator initialized successfully")
    except Exception as e:
        print(f"\nCould not initialize orchestrator: {e}")
        print("This example requires a working orchestrator implementation")
        return
    
    # Create test queries
    test_queries = [
        {
            "query": "What are the key principles of accessible user interface design?",
            "ground_truth": "Key principles include perceivability, operability, understandability, and robustness."
        }
    ]
    
    test_file = Path("data/test_queries_orchestrator.json")
    test_file.parent.mkdir(exist_ok=True)
    with open(test_file, 'w') as f:
        json.dump(test_queries, f, indent=2)
    
    # Initialize evaluator with orchestrator
    evaluator = SystemEvaluator(config, orchestrator=orchestrator)
    
    print("\nRunning evaluation with real orchestrator...")
    print("This will actually query your multi-agent system\n")
    
    # Run evaluation
    report = await evaluator.evaluate_system(str(test_file))
    
    # Display results
    print("\n" + "=" * 70)
    print("EVALUATION RESULTS")
    print("=" * 70)
    print(f"\nTotal Queries: {report['summary']['total_queries']}")
    print(f"Overall Average Score: {report['scores']['overall_average']:.3f}\n")
    
    print("Scores by Criterion:")
    for criterion, score in report['scores']['by_criterion'].items():
        print(f"  {criterion}: {score:.3f}")
    
    # Show detailed result for first query
    if report['detailed_results']:
        result = report['detailed_results'][0]
        print("\n" + "=" * 70)
        print("DETAILED RESULT (First Query)")
        print("=" * 70)
        print(f"\nQuery: {result['query']}")
        print(f"\nResponse: {result['response'][:200]}...")
        print(f"\nOverall Score: {result['evaluation']['overall_score']:.3f}")
    
    print(f"\nFull results saved to outputs/")
    
    # Clean up
    test_file.unlink()


# For direct execution
if __name__ == "__main__":
    import asyncio
    
    print("Running SystemEvaluator Examples\n")
    
    # Run example 1
    asyncio.run(example_simple_evaluation())
    
    print("\n\n")
    
    # Run example 2 (if orchestrator is available)
    asyncio.run(example_with_orchestrator())
