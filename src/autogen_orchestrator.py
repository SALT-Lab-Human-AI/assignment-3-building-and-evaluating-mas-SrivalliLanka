"""
AutoGen-Based Orchestrator

This orchestrator uses AutoGen's RoundRobinGroupChat to coordinate multiple agents
in a research workflow.

Workflow:
1. Planner: Breaks down the query into research steps
2. Researcher: Gathers evidence using web and paper search tools
3. Writer: Synthesizes findings into a coherent response
4. Critic: Evaluates quality and provides feedback
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.messages import TextMessage

from src.agents.autogen_agents import create_research_team
from src.guardrails.safety_manager import SafetyManager


def _run_async_in_thread(coro):
    """
    Helper to run async code in a new event loop in a thread.
    
    This creates a completely isolated event loop to avoid binding conflicts
    with AutoGen's internal async queues and tasks.
    """
    # Create a new event loop for this thread
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    try:
        return new_loop.run_until_complete(coro)
    finally:
        # Clean up: cancel all pending tasks
        try:
            pending = asyncio.all_tasks(new_loop)
            for task in pending:
                task.cancel()
            if pending:
                new_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        finally:
            new_loop.close()


class AutoGenOrchestrator:
    """
    Orchestrates multi-agent research using AutoGen's RoundRobinGroupChat.
    
    This orchestrator manages a team of specialized agents that work together
    to answer research queries. It uses AutoGen's built-in conversation
    management and tool execution capabilities.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the AutoGen orchestrator.

        Args:
            config: Configuration dictionary from config.yaml
        """
        self.config = config
        self.logger = logging.getLogger("autogen_orchestrator")
        
        # Initialize safety manager
        safety_config = config.get("safety", {})
        self.safety_manager = SafetyManager(safety_config) if safety_config.get("enabled", True) else None
        if self.safety_manager:
            self.logger.info("Safety manager initialized")
        
        # Don't create team in __init__ - create it lazily in async context
        # This prevents event loop binding issues when running in threads
        self._team = None
        
        # Workflow trace for debugging and UI display
        self.workflow_trace: List[Dict[str, Any]] = []
    
    async def _get_team_async(self):
        """
        Get or create the research team in the current async context.
        Creates the team lazily to avoid event loop binding issues.
        
        This ensures the team is always created in the same event loop
        where it will be used, preventing "bound to different event loop" errors.
        
        Returns:
            RoundRobinGroupChat team instance
        """
        # Always recreate team in async context to ensure correct event loop binding
        # This is necessary because AutoGen's internal queues are bound to the event loop
        # where the team is created
        self.logger.info("Creating research team in current event loop context...")
        try:
            team = create_research_team(self.config)
            self.logger.info("Research team created successfully")
            return team
        except ValueError as e:
            error_msg = f"Failed to create research team: {e}"
            self.logger.error(error_msg)
            raise ValueError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error creating research team: {e}"
            self.logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e

    def process_query(self, query: str, max_rounds: int = 10) -> Dict[str, Any]:
        """
        Process a research query through the multi-agent system.

        Args:
            query: The research question to answer
            max_rounds: Maximum number of conversation rounds

        Returns:
            Dictionary containing:
            - query: Original query
            - response: Final synthesized response
            - conversation_history: Full conversation between agents
            - metadata: Additional information about the process
            - safety_events: Safety events if any
        """
        self.logger.info(f"Processing query: {query}")
        
        # Check input safety
        if self.safety_manager:
            input_safety = self.safety_manager.check_input_safety(query)
            if not input_safety.get("safe", True):
                violations = input_safety.get("violations", [])
                self.logger.warning(f"Input safety check failed: {violations}")
                
                # Return refusal message
                return {
                    "query": query,
                    "response": self.safety_manager.on_violation.get(
                        "message",
                        "I cannot process this request due to safety policies."
                    ),
                    "conversation_history": [],
                    "metadata": {
                        "safety_blocked": True,
                        "safety_violations": violations,
                        "num_messages": 0,
                        "num_sources": 0
                    },
                    "safety_events": [{
                        "type": "input",
                        "safe": False,
                        "violations": violations
                    }]
                }
        
        try:
            # Run the async query processing
            # Always use asyncio.run() to create a fresh event loop
            # This ensures the team is created in the same event loop where it runs
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're already in an async context (e.g., Streamlit), 
                    # we need to run in a separate thread with a new event loop
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(_run_async_in_thread, self._process_query_async(query, max_rounds))
                        result = future.result(timeout=self.config.get("system", {}).get("timeout_seconds", 300) + 60)
                else:
                    # No running loop, but one exists - use asyncio.run() to create fresh
                    result = asyncio.run(self._process_query_async(query, max_rounds))
            except RuntimeError:
                # No event loop exists, create a new one with asyncio.run()
                result = asyncio.run(self._process_query_async(query, max_rounds))
            
            # Check output safety
            if self.safety_manager and "response" in result:
                output_safety = self.safety_manager.check_output_safety(
                    result.get("response", ""),
                    result.get("metadata", {}).get("sources", [])
                )
                
                if not output_safety.get("safe", True):
                    violations = output_safety.get("violations", [])
                    self.logger.warning(f"Output safety check failed: {violations}")
                    
                    # Update response based on safety action
                    result["response"] = output_safety.get("response", result.get("response", ""))
                    result["metadata"]["safety_blocked"] = True
                    result["metadata"]["safety_violations"] = violations
                
                # Add safety events to metadata
                safety_events = self.safety_manager.get_safety_events()
                if safety_events:
                    result["safety_events"] = safety_events[-5:]  # Last 5 events
                    result["metadata"]["safety_events"] = safety_events[-5:]
            
            self.logger.info("Query processing complete")
            return result
            
        except ValueError as e:
            # API connection or configuration errors
            error_msg = str(e)
            self.logger.error(f"Configuration/API error: {error_msg}", exc_info=True)
            return {
                "query": query,
                "error": error_msg,
                "response": f"API connection error: {error_msg}. Please check your API keys and configuration.",
                "conversation_history": [],
                "metadata": {"error": True, "error_type": "api_connection"}
            }
        except Exception as e:
            # Other errors
            error_msg = str(e)
            self.logger.error(f"Error processing query: {error_msg}", exc_info=True)
            return {
                "query": query,
                "error": error_msg,
                "response": f"An error occurred while processing your query: {error_msg}",
                "conversation_history": [],
                "metadata": {"error": True, "error_type": "orchestrator_error"}
            }
    
    async def _process_query_async(self, query: str, max_rounds: int = 10) -> Dict[str, Any]:
        """
        Async implementation of query processing.
        
        Args:
            query: The research question to answer
            max_rounds: Maximum number of conversation rounds (default 10 for faster processing)
            
        Returns:
            Dictionary containing results
        """
        # Create task message
        task_message = f"""Research Query: {query}

Please work together to answer this query comprehensively:
1. Planner: Create a research plan
2. Researcher: Gather evidence from web and academic sources
3. Writer: Synthesize findings into a well-cited response
4. Critic: Evaluate the quality and provide feedback"""
        
        # Get or create team in this async context (lazy creation)
        # This ensures the team is bound to the current event loop
        # We create it fresh each time to avoid event loop binding issues
        team = await self._get_team_async()
        
        # Run the team with timeout
        try:
            # Add timeout to prevent infinite execution
            timeout_seconds = self.config.get("system", {}).get("timeout_seconds", 300)
            result = await asyncio.wait_for(
                team.run(task=task_message),
                timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            error_msg = f"Query processing timed out after {timeout_seconds} seconds"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Error during team execution: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            # Re-raise with more context
            if "api" in str(e).lower() or "connection" in str(e).lower() or "key" in str(e).lower():
                raise ValueError(f"API connection error: {e}") from e
            raise RuntimeError(error_msg) from e
        
        # Extract conversation history
        messages = []
        # result.messages might be a list or an async iterator
        if hasattr(result.messages, '__aiter__'):
            # It's an async iterator
            async for message in result.messages:
                msg_dict = {
                    "source": message.source,
                    "content": message.content if hasattr(message, 'content') else str(message),
                }
                messages.append(msg_dict)
        else:
            # It's a regular list/iterable
            for message in result.messages:
                msg_dict = {
                    "source": message.source,
                    "content": message.content if hasattr(message, 'content') else str(message),
                }
                messages.append(msg_dict)
        
        # Limit conversation history to prevent context length issues
        # Keep only the most recent messages (last 20 messages max)
        max_messages = 20  # Reduced from 50 for efficient 6-query evaluation
        if len(messages) > max_messages:
            self.logger.warning(
                f"Conversation history too long ({len(messages)} messages), "
                f"keeping only last {max_messages} messages"
            )
            # Keep first message (query) and last N messages
            messages = [messages[0]] + messages[-max_messages+1:]
        
        # Extract final response
        final_response = ""
        if messages:
            # Get the last message from Writer or Critic
            for msg in reversed(messages):
                if msg.get("source") in ["Writer", "Critic"]:
                    final_response = msg.get("content", "")
                    break
        
        # If no response found, use the last message
        if not final_response and messages:
            final_response = messages[-1].get("content", "")
        
        return self._extract_results(query, messages, final_response)

    def _extract_results(self, query: str, messages: List[Dict[str, Any]], final_response: str = "") -> Dict[str, Any]:
        """
        Extract structured results from the conversation history.

        Args:
            query: Original query
            messages: List of conversation messages
            final_response: Final response from the team

        Returns:
            Structured result dictionary
        """
        # Extract components from conversation
        research_findings = []
        plan = ""
        critique = ""
        
        for msg in messages:
            source = msg.get("source", "")
            content = msg.get("content", "")
            
            if source == "Planner" and not plan:
                plan = content
            
            elif source == "Researcher":
                research_findings.append(content)
            
            elif source == "Critic":
                critique = content
        
        # Count sources mentioned in research
        num_sources = 0
        for finding in research_findings:
            # Rough count of sources based on numbered results
            num_sources += finding.count("\n1.") + finding.count("\n2.") + finding.count("\n3.")
        
        # Clean up final response
        if final_response:
            final_response = final_response.replace("TERMINATE", "").strip()
        
        return {
            "query": query,
            "response": final_response,
            "conversation_history": messages,
            "metadata": {
                "num_messages": len(messages),
                "num_sources": max(num_sources, 1),  # At least 1
                "plan": plan,
                "research_findings": research_findings,
                "critique": critique,
                "agents_involved": list(set([msg.get("source", "") for msg in messages])),
            }
        }

    def get_agent_descriptions(self) -> Dict[str, str]:
        """
        Get descriptions of all agents.

        Returns:
            Dictionary mapping agent names to their descriptions
        """
        return {
            "Planner": "Breaks down research queries into actionable steps",
            "Researcher": "Gathers evidence from web and academic sources",
            "Writer": "Synthesizes findings into coherent responses",
            "Critic": "Evaluates quality and provides feedback",
        }

    def visualize_workflow(self) -> str:
        """
        Generate a text visualization of the workflow.

        Returns:
            String representation of the workflow
        """
        workflow = """
AutoGen Research Workflow:

1. User Query
   ↓
2. Planner
   - Analyzes query
   - Creates research plan
   - Identifies key topics
   ↓
3. Researcher (with tools)
   - Uses web_search() tool
   - Uses paper_search() tool
   - Gathers evidence
   - Collects citations
   ↓
4. Writer
   - Synthesizes findings
   - Creates structured response
   - Adds citations
   ↓
5. Critic
   - Evaluates quality
   - Checks completeness
   - Provides feedback
   ↓
6. Decision Point
   - If APPROVED → Final Response
   - If NEEDS REVISION → Back to Writer
        """
        return workflow


def demonstrate_usage():
    """
    Demonstrate how to use the AutoGen orchestrator.
    
    This function shows a simple example of using the orchestrator.
    """
    import yaml
    from dotenv import load_dotenv
    
    # Load environment variables
    load_dotenv()
    
    # Load configuration
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
    
    # Create orchestrator
    orchestrator = AutoGenOrchestrator(config)
    
    # Print workflow visualization
    print(orchestrator.visualize_workflow())
    
    # Example query
    query = "What are the latest trends in human-computer interaction research?"
    
    print(f"\nProcessing query: {query}\n")
    print("=" * 70)
    
    # Process query
    result = orchestrator.process_query(query)
    
    # Display results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"\nQuery: {result['query']}")
    print(f"\nResponse:\n{result['response']}")
    print(f"\nMetadata:")
    print(f"  - Messages exchanged: {result['metadata']['num_messages']}")
    print(f"  - Sources gathered: {result['metadata']['num_sources']}")
    print(f"  - Agents involved: {', '.join(result['metadata']['agents_involved'])}")


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    demonstrate_usage()

