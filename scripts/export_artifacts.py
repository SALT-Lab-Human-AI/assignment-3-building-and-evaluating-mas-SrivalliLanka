"""
Export Artifacts Script
Generates sample conversation JSON, response Markdown/HTML, and evaluation results.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import yaml
from dotenv import load_dotenv
from src.autogen_orchestrator import AutoGenOrchestrator
from src.evaluation.evaluator import SystemEvaluator

load_dotenv()


def export_sample_conversation(config_path: str = "config.yaml", query: str = None):
    """Export a sample conversation as JSON."""
    print("=" * 70)
    print("EXPORTING SAMPLE CONVERSATION")
    print("=" * 70)
    
    # Load config
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Initialize orchestrator
    orchestrator = AutoGenOrchestrator(config)
    
    # Use provided query or default
    if not query:
        query = "What are the key principles of explainable AI for novice users?"
    
    print(f"\nProcessing query: {query}\n")
    
    # Process query
    result = orchestrator.process_query(query)
    
    # Clean result for JSON serialization (remove non-serializable objects)
    def clean_for_json(obj):
        """Recursively clean object for JSON serialization."""
        if isinstance(obj, dict):
            return {k: clean_for_json(v) for k, v in obj.items() if not k.startswith('_')}
        elif isinstance(obj, list):
            return [clean_for_json(item) for item in obj]
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        else:
            # Convert non-serializable objects to string
            return str(obj)
    
    cleaned_result = clean_for_json(result)
    
    # Export to outputs/
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"sample_conversation_{timestamp}.json"
    filepath = output_dir / filename
    
    with open(filepath, 'w') as f:
        json.dump(cleaned_result, f, indent=2)
    
    print(f"✅ Exported conversation to {filepath}")
    return filepath


def export_response_markdown(conversation_json_path: str = None):
    """Export response as Markdown from conversation JSON."""
    print("=" * 70)
    print("EXPORTING RESPONSE AS MARKDOWN")
    print("=" * 70)
    
    if conversation_json_path:
        with open(conversation_json_path, 'r') as f:
            result = json.load(f)
    else:
        # Generate a new conversation
        filepath = export_sample_conversation()
        with open(filepath, 'r') as f:
            result = json.load(f)
    
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"response_{timestamp}.md"
    filepath = output_dir / filename
    
    markdown = f"""# Research Response

**Query:** {result.get('query', 'Unknown')}

**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Response

{result.get('response', '')}

## Citations

"""
    
    # Extract citations
    citations = []
    for msg in result.get("conversation_history", []):
        content = msg.get("content", "")
        # Ensure content is a string
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        elif not isinstance(content, str):
            content = str(content) if content else ""
        import re
        urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', content)
        citations.extend(urls)
    
    citations = list(set(citations))[:15]  # Deduplicate and limit
    
    for i, citation in enumerate(citations, 1):
        markdown += f"{i}. [{citation}]({citation})\n"
    
    metadata = result.get("metadata", {})
    markdown += f"\n## Metadata\n\n"
    markdown += f"- Sources Used: {metadata.get('num_sources', 0)}\n"
    markdown += f"- Agent Messages: {metadata.get('num_messages', 0)}\n"
    markdown += f"- Quality Score: {metadata.get('critique_score', 0):.2f}\n"
    
    # Safety events
    safety_events = result.get("safety_events", [])
    if safety_events:
        markdown += f"\n## Safety Events\n\n"
        for event in safety_events:
            event_type = event.get("type", "unknown")
            is_safe = event.get("safe", True)
            markdown += f"- **{event_type.upper()}**: {'✅ Safe' if is_safe else '⚠️ Violations'}\n"
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(markdown)
    
    print(f"✅ Exported Markdown to {filepath}")
    return filepath


def export_evaluation_results(config_path: str = "config.yaml"):
    """Export evaluation results."""
    print("=" * 70)
    print("EXPORTING EVALUATION RESULTS")
    print("=" * 70)
    
    import asyncio
    
    # Load config
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Initialize orchestrator and evaluator
    orchestrator = AutoGenOrchestrator(config)
    evaluator = SystemEvaluator(config, orchestrator=orchestrator)
    
    # Run evaluation
    print("\nRunning evaluation...")
    report = asyncio.run(evaluator.evaluate_system("data/example_queries.json"))
    
    # Export is already done by evaluator, just confirm
    print("\n✅ Evaluation results exported to outputs/")
    print(f"   - JSON: evaluation_*.json")
    print(f"   - Summary: evaluation_summary_*.txt")
    print(f"   - Markdown: evaluation_report_*.md")
    
    return report


def main():
    """Main export function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Export artifacts from the research system")
    parser.add_argument(
        "--type",
        choices=["conversation", "markdown", "evaluation", "all"],
        default="all",
        help="Type of artifact to export"
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Query to use for conversation/markdown export"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file"
    )
    
    args = parser.parse_args()
    
    if args.type == "conversation" or args.type == "all":
        export_sample_conversation(args.config, args.query)
        print()
    
    if args.type == "markdown" or args.type == "all":
        export_response_markdown()
        print()
    
    if args.type == "evaluation" or args.type == "all":
        export_evaluation_results(args.config)
        print()
    
    print("=" * 70)
    print("EXPORT COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()

