"""
Export Judge Outputs Script
Extracts judge prompts and outputs from evaluation results.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def export_judge_outputs(evaluation_json_path: str = None):
    """Export judge prompts and outputs from evaluation results."""
    print("=" * 70)
    print("EXPORTING JUDGE OUTPUTS")
    print("=" * 70)
    
    # Find the most recent evaluation file if not specified
    if not evaluation_json_path:
        output_dir = Path("outputs")
        if not output_dir.exists():
            print("❌ No outputs directory found. Run evaluation first.")
            return
        
        eval_files = list(output_dir.glob("evaluation_*.json"))
        if not eval_files:
            print("❌ No evaluation files found. Run evaluation first.")
            return
        
        # Get most recent
        evaluation_json_path = str(max(eval_files, key=lambda p: p.stat().st_mtime))
        print(f"Using evaluation file: {evaluation_json_path}\n")
    
    # Load evaluation results
    with open(evaluation_json_path, 'r', encoding='utf-8') as f:
        evaluation_data = json.load(f)
    
    # Find a representative query with evaluation data
    detailed_results = evaluation_data.get("detailed_results", [])
    if not detailed_results:
        print("❌ No detailed results found in evaluation file.")
        return
    
    # Get first successful result
    representative_result = None
    for result in detailed_results:
        if "evaluation" in result and "error" not in result:
            representative_result = result
            break
    
    if not representative_result:
        print("❌ No successful evaluation results found.")
        return
    
    # Extract judge outputs
    query = representative_result.get("query", "")
    evaluation = representative_result.get("evaluation", {})
    criterion_scores = evaluation.get("criterion_scores", {})
    
    # Create judge outputs document
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"judge_outputs_{timestamp}.json"
    filepath = output_dir / filename
    
    judge_outputs = {
        "query": query,
        "response": representative_result.get("response", "")[:500] + "..." if len(representative_result.get("response", "")) > 500 else representative_result.get("response", ""),
        "overall_score": evaluation.get("overall_score", 0.0),
        "judge_evaluations": {}
    }
    
    # Extract judge perspectives for each criterion
    for criterion_name, score_data in criterion_scores.items():
        if isinstance(score_data, dict):
            perspectives = score_data.get("perspectives", [])
            judge_outputs["judge_evaluations"][criterion_name] = {
                "average_score": score_data.get("score", 0.0),
                "reasoning": score_data.get("reasoning", ""),
                "perspectives": perspectives
            }
    
    # Save judge outputs
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(judge_outputs, f, indent=2)
    
    print(f"✅ Exported judge outputs to {filepath}")
    print(f"\nQuery: {query[:100]}...")
    print(f"Overall Score: {judge_outputs['overall_score']:.3f}")
    print(f"Criteria Evaluated: {len(judge_outputs['judge_evaluations'])}")
    
    return filepath


def main():
    """Main export function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Export judge outputs from evaluation results")
    parser.add_argument(
        "--evaluation-file",
        type=str,
        help="Path to evaluation JSON file (default: most recent)"
    )
    
    args = parser.parse_args()
    
    export_judge_outputs(args.evaluation_file)
    
    print("\n" + "=" * 70)
    print("EXPORT COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()

