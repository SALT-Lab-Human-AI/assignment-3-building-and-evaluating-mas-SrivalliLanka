# Limitations for 5 Queries Evaluation

## Current Configuration

- **Queries:** 3 (optimized for speed)
- **Timeout:** 120 seconds per query
- **Max Rounds:** 3 per query
- **Max Messages:** 50 messages in conversation history
- **Model:** gpt-4o-mini (128k token context limit)

## Limitations When Scaling to 5 Queries

### 1. ⏱️ **Time Limitations**

**Current (3 queries):**
- Per query: ~1.5-2 minutes
- Total: ~4.5-6 minutes

**With 5 queries:**
- Per query: ~1.5-2 minutes
- Total: ~7.5-10 minutes
- **66% longer evaluation time**

**Impact:**
- Longer wait time for results
- More time for errors to accumulate
- Higher chance of timeout issues

---

### 2. 🎯 **Context Length Limitations** (CRITICAL)

**Problem:** Query 2 already exceeded 128k token limit (129,705 tokens)

**Current Protection:**
- Limited to 50 messages in conversation history
- But this happens AFTER extraction, not during conversation

**With 5 queries:**
- Each query adds ~20-30 messages to conversation
- Agent conversations can grow very long
- **High risk of context length errors**

**What Happens:**
```
Error: This model's maximum context length is 128000 tokens. 
However, your messages resulted in 129705 tokens
```

**Solutions Needed:**
1. ✅ Reduce max_rounds further (3 → 2)
2. ✅ Limit conversation history during agent execution (not just after)
3. ✅ Summarize old messages instead of keeping full history
4. ✅ Use shorter system prompts
5. ✅ Reduce max_tokens for responses

---

### 3. 💰 **API Cost Limitations**

**Current (3 queries):**
- ~45-60 API calls total
- Cost: ~$0.10-0.15

**With 5 queries:**
- ~75-100 API calls total
- Cost: ~$0.17-0.25
- **66% higher cost**

**Breakdown per query:**
- Agents: 8-12 calls (Planner, Researcher, Writer, Critic)
- Judge: 10 calls (5 criteria × 2 perspectives)
- Safety: 1-2 calls
- **Total: ~19-24 calls per query**

---

### 4. 🧠 **Memory Limitations**

**Current (3 queries):**
- Results stored: ~5-10 MB
- Conversation history: ~2-5 MB per query

**With 5 queries:**
- Results stored: ~8-15 MB
- Conversation history: ~10-25 MB total
- **66% more memory usage**

**Impact:**
- Slower JSON serialization
- Larger output files
- More disk space needed

---

### 5. ⚠️ **Error Accumulation**

**Current (3 queries):**
- 1 error = 33% failure rate
- System can handle 1-2 errors gracefully

**With 5 queries:**
- 1 error = 20% failure rate (better)
- But more chances for errors:
  - Context length errors (more likely)
  - Timeout errors (more likely)
  - API rate limit errors (more likely)
  - Network errors (more likely)

**Impact:**
- Higher probability of at least one error
- Need better error recovery
- May need to re-run failed queries

---

### 6. 🔄 **Conversation History Growth**

**Problem:** Each query's conversation history accumulates

**Current Protection:**
- Limited to 50 messages AFTER extraction
- But during agent execution, full history is used

**With 5 queries:**
- If agents reference previous queries, history grows
- Each agent round adds messages
- **Exponential growth risk**

**Example:**
- Query 1: 20 messages
- Query 2: 20 messages (but sees Query 1's 20 = 40 total)
- Query 3: 20 messages (sees 40 = 60 total)
- Query 4: 20 messages (sees 60 = 80 total)
- Query 5: 20 messages (sees 80 = 100 total)
- **Total: 100+ messages = context length exceeded**

---

## Required Adjustments for 5 Queries

### ✅ 1. Reduce Max Rounds Further

**Current:** `max_rounds=3`
**Recommended:** `max_rounds=2`

**Location:** `src/evaluation/evaluator.py` line 171

```python
response_data = self.orchestrator.process_query(query, max_rounds=2)  # Reduced from 3
```

**Impact:**
- 33% fewer agent interactions
- Shorter conversations
- Less context length usage

---

### ✅ 2. Limit Conversation History During Execution

**Current:** Only limits AFTER extraction
**Needed:** Limit DURING agent execution

**Location:** `src/autogen_orchestrator.py`

**Solution:** Implement message summarization or truncation in the team execution

**Challenge:** AutoGen manages conversation internally, hard to intercept

**Workaround:** Reduce max_rounds (already recommended above)

---

### ✅ 3. Reduce Token Limits Further

**Current:**
- Agents: `max_tokens: 1024`
- Judge: `max_tokens: 512`

**Recommended:**
- Agents: `max_tokens: 512` (50% reduction)
- Judge: `max_tokens: 256` (50% reduction)

**Location:** `config.yaml`

```yaml
models:
  default:
    max_tokens: 512  # Reduced from 1024
  judge:
    max_tokens: 256  # Reduced from 512
```

**Impact:**
- Shorter responses
- Less context usage
- Faster API calls

---

### ✅ 4. Increase Timeout Buffer

**Current:** `timeout_seconds: 120`
**Recommended:** `timeout_seconds: 180` (back to original)

**Location:** `config.yaml`

```yaml
system:
  timeout_seconds: 180  # Increased from 120 for 5 queries
```

**Impact:**
- More time for complex queries
- Less timeout errors
- But longer total evaluation time

---

### ✅ 5. Implement Conversation History Summarization

**Idea:** Summarize old messages instead of keeping full history

**Implementation:**
- After each query, summarize conversation history
- Keep only summary + recent messages
- Reduces context length significantly

**Complexity:** High (requires modifying AutoGen behavior)

**Alternative:** Just reduce max_rounds (simpler)

---

### ✅ 6. Add Better Error Recovery

**Current:** Errors stop evaluation
**Recommended:** Retry failed queries automatically

**Implementation:**
- Track failed queries
- Retry with reduced max_rounds
- Continue evaluation even if some queries fail

---

## Recommended Configuration for 5 Queries

### `config.yaml` Changes:

```yaml
system:
  timeout_seconds: 180  # Increased for 5 queries
  api_timeout: 60
  api_retry_attempts: 3
  api_retry_backoff: 1.0

models:
  default:
    max_tokens: 512  # Reduced from 1024
  judge:
    max_tokens: 256  # Reduced from 512

evaluation:
  num_test_queries: 5  # Changed from 3
```

### `src/evaluation/evaluator.py` Changes:

```python
# Line 171
response_data = self.orchestrator.process_query(query, max_rounds=2)  # Reduced from 3
```

### `src/autogen_orchestrator.py` Changes:

```python
# Line 291 - Already implemented
max_messages = 30  # Reduced from 50 for 5 queries
```

---

## Expected Performance with 5 Queries

### Time:
- **Per query:** ~1-1.5 minutes (with optimizations)
- **Total:** ~5-7.5 minutes

### Success Rate:
- **With optimizations:** ~80-90% (4-5 successful queries)
- **Without optimizations:** ~60-70% (3-4 successful queries)

### Context Length:
- **Risk:** Medium-High (even with optimizations)
- **Mitigation:** Reduced max_rounds, reduced tokens, message limiting

### API Costs:
- **Total:** ~$0.17-0.25
- **Per query:** ~$0.03-0.05

---

## Risk Assessment

### High Risk:
- ⚠️ **Context length exceeded** (already happened with Query 2)
- ⚠️ **Timeout errors** (more queries = more time = more timeouts)

### Medium Risk:
- ⚠️ **API rate limits** (more calls = higher chance of 429 errors)
- ⚠️ **Memory issues** (larger result files)

### Low Risk:
- ✅ **JSON serialization** (already fixed)
- ✅ **Error handling** (already implemented)

---

## Recommendations

### Option 1: Use 5 Queries with Optimizations (Recommended)
- ✅ Apply all optimizations above
- ✅ Accept ~20% failure rate
- ✅ Re-run failed queries manually if needed
- **Time:** 5-7.5 minutes
- **Success Rate:** ~80-90%

### Option 2: Use 3 Queries (Current - Safest)
- ✅ Already optimized
- ✅ Lower failure rate
- ✅ Faster evaluation
- **Time:** 4.5-6 minutes
- **Success Rate:** ~90-95%

### Option 3: Use 5 Queries with Aggressive Optimizations
- ✅ max_rounds=2
- ✅ max_tokens=256 for agents
- ✅ max_messages=20
- ✅ Accept lower quality for speed
- **Time:** 4-6 minutes
- **Success Rate:** ~70-80%

---

## Conclusion

**For 5 queries, you need to:**
1. ✅ Reduce max_rounds to 2
2. ✅ Reduce max_tokens further
3. ✅ Increase timeout to 180s
4. ✅ Accept higher failure rate (~20%)
5. ✅ Be prepared to re-run failed queries

**The main limitation is context length** - Query 2 already exceeded it. With 5 queries, this risk increases significantly unless you apply aggressive optimizations.

**Recommendation:** Start with 3 queries (current setup), then scale to 5 queries with all optimizations applied if needed.

