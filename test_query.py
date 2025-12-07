"""
Simple test script to test the multi-agent system with a query.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import yaml
import asyncio
from dotenv import load_dotenv
from src.autogen_orchestrator import AutoGenOrchestrator

# Load environment variables
load_dotenv()

def test_query():
    """Test the system with a simple query."""
    print("=" * 70)
    print("TESTING MULTI-AGENT RESEARCH SYSTEM")
    print("=" * 70)
    print()
    
    # Load configuration
    try:
        with open("config.yaml", 'r') as f:
            config = yaml.safe_load(f)
        print("✓ Configuration loaded")
    except Exception as e:
        print(f"✗ Error loading config: {e}")
        return
    
    # Initialize orchestrator
    try:
        print("Initializing AutoGen orchestrator...")
        orchestrator = AutoGenOrchestrator(config)
        print("✓ Orchestrator initialized")
    except Exception as e:
        print(f"✗ Error initializing orchestrator: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test query
    test_query = "What are the key principles of explainable AI for novice users?"
    
    print("\n" + "=" * 70)
    print(f"TEST QUERY: {test_query}")
    print("=" * 70)
    print()
    
    try:
        # Process the query
        print("Processing query through multi-agent system...")
        print("This may take a few moments...\n")
        
        result = orchestrator.process_query(test_query, max_rounds=10)
        
        # Display results
        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70)
        print()
        
        print(f"Query: {result.get('query', 'N/A')}")
        print()
        
        if 'error' in result:
            print(f"❌ Error: {result['error']}")
            return
        
        print("Response:")
        print("-" * 70)
        response = result.get('response', 'No response generated')
        print(response)
        print("-" * 70)
        print()
        
        # Metadata
        metadata = result.get('metadata', {})
        print("Metadata:")
        print(f"  - Messages exchanged: {metadata.get('num_messages', 0)}")
        print(f"  - Sources gathered: {metadata.get('num_sources', 0)}")
        print(f"  - Agents involved: {', '.join(metadata.get('agents_involved', []))}")
        
        # Safety events
        safety_events = result.get('safety_events', [])
        if safety_events:
            print(f"\nSafety Events: {len(safety_events)}")
            for event in safety_events:
                print(f"  - Type: {event.get('type')}, Safe: {event.get('safe')}")
        
        # Conversation history preview
        conversation = result.get('conversation_history', [])
        if conversation:
            print(f"\nConversation History ({len(conversation)} messages):")
            print("  Preview of first few messages:")
            for i, msg in enumerate(conversation[:3], 1):
                source = msg.get('source', 'Unknown')
                content = msg.get('content', '')[:100]
                print(f"    {i}. [{source}]: {content}...")
        
        print("\n" + "=" * 70)
        print("TEST COMPLETED SUCCESSFULLY")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Error processing query: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_query()


