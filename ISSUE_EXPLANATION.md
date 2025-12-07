# Issue Explanation: Why the System Was Running Indefinitely

## What is `run_forever()`?

`run_forever()` is a method in Python's `asyncio` event loop that runs the event loop indefinitely until `stop()` is called. It's part of the asyncio infrastructure that manages asynchronous operations.

In your code, when you call:
```python
result = loop.run_until_complete(self._process_query_async(query, max_rounds))
```

The `run_until_complete()` method internally calls `run_forever()` to keep the event loop running until the coroutine completes.

## Why Was It Running Indefinitely?

The system was running indefinitely because of **excessive API calls to Semantic Scholar**. Here's what was happening:

### The Problem

1. **Semantic Scholar Iterator Issue**: The `semanticscholar` library's `search_paper()` method returns an **iterator** that automatically paginates through ALL available results. When you iterate over it, it keeps making API calls to fetch more and more papers.

2. **No Result Limiting**: The code was iterating over the entire iterator without stopping, causing:
   - Hundreds of API calls (we saw 800+ papers being fetched)
   - Rate limiting (429 errors from Semantic Scholar)
   - Long wait times (30+ seconds per rate limit)
   - The event loop waiting for all these API calls to complete

3. **Agent Behavior**: The researcher agent might have been calling `paper_search` multiple times, each time triggering this excessive fetching.

### The Fix

I've implemented several fixes:

1. **Strict Result Limiting** (`src/tools/paper_search.py`):
   - Convert the iterator to a list immediately
   - Limit to `max_results` (default 10) before any further processing
   - Cap the API limit parameter at 50 to prevent excessive initial fetches

2. **Timeout Protection** (`src/autogen_orchestrator.py`):
   - Added `asyncio.wait_for()` with a timeout (default 300 seconds from config)
   - Prevents the system from running forever if something goes wrong

3. **Better Agent Instructions** (`src/agents/autogen_agents.py`):
   - Updated the researcher agent's system prompt to explicitly limit searches
   - Instructs the agent to use `max_results=10` for paper_search and `max_results=5` for web_search
   - Tells the agent to stop after gathering 5-10 sources total

### How to Verify the Fix

Run the test again:
```bash
python test_simple_query.py
```

The query should now complete in a reasonable time (1-3 minutes instead of running indefinitely).

### Key Takeaways

- **Event loops run until tasks complete**: `run_forever()` keeps running until all async tasks finish
- **Iterators can be dangerous**: Some libraries return iterators that fetch data lazily, which can cause unexpected behavior
- **Always limit API calls**: Set strict limits on external API calls to prevent runaway processes
- **Add timeouts**: Always add timeouts to long-running operations to prevent infinite waits

