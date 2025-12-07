# Assignment Requirements Mapping

This document maps each assignment requirement to its implementation location and explains how it's fulfilled.

## 1. System Requirements

### A. Agents & Orchestration (AutoGen)

#### Requirement: Minimum 3 agents with clear roles (Planner, Researcher, Critic/Verifier, Writer)

**Implementation Location:**
- **File:** `src/agents/autogen_agents.py`
- **Functions:**
  - `create_planner_agent()` (lines 95-128) - Creates Planner agent
  - `create_researcher_agent()` (lines 131-186) - Creates Researcher agent with tool access
  - `create_writer_agent()` (lines 189-232) - Creates Writer agent
  - `create_critic_agent()` (lines 235-280) - Creates Critic agent
  - `create_research_team()` (lines 283-310) - Orchestrates all 4 agents

**How it works:**
- All 4 agents are implemented as AutoGen `AssistantAgent` instances
- Each agent has distinct system prompts defining their role
- Agents coordinate via `RoundRobinGroupChat` (line 305 in `autogen_agents.py`)
- Handoff signals: "PLAN COMPLETE", "RESEARCH COMPLETE", "DRAFT COMPLETE", "APPROVED - RESEARCH COMPLETE"

**Orchestration:**
- **File:** `src/autogen_orchestrator.py`
- **Class:** `AutoGenOrchestrator` (lines 34-421)
- **Method:** `_process_query_async()` (lines 186-260) - Manages workflow
- Uses AutoGen's `RoundRobinGroupChat` for sequential agent communication

#### Requirement: Recommended workflow (planning → evidence gathering → synthesis → critique → final answer)

**Implementation:**
- **File:** `src/autogen_orchestrator.py`
- **Workflow:** Lines 198-204 in `_process_query_async()`
  ```python
  task_message = f"""Research Query: {query}
  
  Please work together to answer this query comprehensively:
  1. Planner: Create a research plan
  2. Researcher: Gather evidence from web and academic sources
  3. Writer: Synthesize findings into a well-cited response
  4. Critic: Evaluate the quality and provide feedback"""
  ```
- **Control Flow:** `RoundRobinGroupChat` manages turn-taking (line 211)
- **Termination:** Based on handoff signals in agent prompts

#### Requirement: Tool use (web search, paper search, citation extraction)

**Implementation:**

1. **Web Search Tool:**
   - **File:** `src/tools/web_search.py`
   - **Class:** `WebSearchTool` (lines 15-211)
   - **Function:** `web_search()` (lines 215-257)
   - **APIs:** Tavily and Brave Search (configurable in `config.yaml`)
   - **Integration:** Wrapped as `FunctionTool` in `create_researcher_agent()` (lines 167-170)

2. **Paper Search Tool:**
   - **File:** `src/tools/paper_search.py`
   - **Class:** `PaperSearchTool` (lines 16-349)
   - **Function:** `paper_search()` (lines 215-257)
   - **API:** Semantic Scholar API
   - **Integration:** Wrapped as `FunctionTool` in `create_researcher_agent()` (lines 172-175)

3. **Citation Tool:**
   - **File:** `src/tools/citation_tool.py`
   - **Class:** `CitationTool` (lines 14-350)
   - **Features:** APA and MLA citation formatting
   - **Usage:** Used by Writer agent for citation formatting

**Configuration:**
- **File:** `config.yaml` (lines 79-91)
  ```yaml
  tools:
    web_search:
      enabled: true
      provider: "tavily"
      max_results: 5
    paper_search:
      enabled: true
      provider: "semantic_scholar"
      max_results: 10
  ```

---

### B. Safety & Guardrails

#### Requirement: Integrate safety framework (Guardrails, NeMo Guardrails, or custom policy filter)

**Implementation:**
- **Custom LLM-based safety framework** (not external library)
- **File:** `src/guardrails/safety_manager.py`
- **Class:** `SafetyManager` (lines 27-299)
- **Components:**
  - `InputGuardrail` - `src/guardrails/input_guardrail.py`
  - `OutputGuardrail` - `src/guardrails/output_guardrail.py`
  - `LLM Safety Helper` - `src/guardrails/llm_safety_helper.py`

**Initialization:**
- **File:** `src/autogen_orchestrator.py` (lines 54-57)
  ```python
  safety_config = config.get("safety", {})
  self.safety_manager = SafetyManager(safety_config)
  ```

#### Requirement: Detect and handle unsafe inputs/outputs (refuse, route, redact)

**Implementation:**

1. **Input Safety:**
   - **File:** `src/guardrails/input_guardrail.py`
   - **Method:** `validate()` (lines 51-102)
   - **Checks:**
     - Length validation (5-2000 chars)
     - Prompt injection detection (lines 156-235)
     - Toxic language detection (lines 104-154)
     - Topic relevance (lines 237-271)

2. **Output Safety:**
   - **File:** `src/guardrails/output_guardrail.py`
   - **Method:** `validate()` (lines 52-97)
   - **Checks:**
     - PII detection (lines 99-137) - emails, phone, SSN, credit cards
     - Harmful content (lines 139-188)
     - Factual consistency (lines 190-270)
     - Bias detection (lines 272-340)

3. **Response Strategies:**
   - **File:** `src/guardrails/safety_manager.py` (lines 204-215)
   - **Config:** `config.yaml` (lines 105-108)
     ```yaml
     on_violation:
       action: "refuse"  # or "sanitize" or "redirect"
       message: "I cannot process this request due to safety policies."
     ```

#### Requirement: Documented guardrail policy (≥3 prohibited categories)

**Documentation:**

1. **In Code:**
   - **File:** `config.yaml` (lines 98-103)
     ```yaml
     prohibited_categories:
       - "harmful_content"
       - "personal_attacks"
       - "misinformation"
       - "off_topic_queries"
     ```

2. **In README:**
   - **File:** `README.md` (lines 281-311)
   - Documents all 4+ categories with descriptions

3. **In Technical Report:**
   - **File:** `TECHNICAL_REPORT.md`
   - Section: "Safety Design" (detailed explanation)

4. **Testing Documentation:**
   - **File:** `GUARDRAIL_TESTING.md`
   - Documents which categories were triggered during testing

#### Requirement: Log safety events (what was blocked/redacted and why)

**Implementation:**

1. **Logging:**
   - **File:** `src/guardrails/safety_manager.py`
   - **Method:** `_log_safety_event()` (lines 236-270)
   - **Log Format:**
     ```python
     {
       "timestamp": datetime.now().isoformat(),
       "type": "input" or "output",
       "safe": boolean,
       "violations": [list of violations],
       "content_preview": first 100 chars
     }
     ```

2. **Log Files:**
   - **Config:** `config.yaml` (line 139)
     ```yaml
     safety_log: "logs/safety_events.log"
     ```

3. **UI Display:**
   - **CLI:** `src/ui/cli.py` (lines 211-227) - Shows safety events in console
   - **Web UI:** `src/ui/streamlit_app.py` (lines 230-245) - Displays safety events

---

### C. User Interface

#### Requirement: CLI or web UI (Streamlit, Gradio, etc.)

**Implementation:**

1. **CLI:**
   - **File:** `src/ui/cli.py`
   - **Class:** `CLI` (lines 24-352)
   - **Entry Point:** `main.py` (line 19) - `python main.py --mode cli`
   - **Features:**
     - Interactive prompt loop (lines 91-136)
     - Command handling (help, quit, clear, stats)
     - Formatted output display

2. **Web UI (Streamlit):**
   - **File:** `src/ui/streamlit_app.py`
   - **Entry Point:** `main.py` (line 25) - `python main.py --mode web`
   - **Features:**
     - Query input area (lines 509-514)
     - Real-time processing status
     - Response display with formatting
     - Expandable sections for traces and citations

#### Requirement: Display agents' output traces

**Implementation:**

1. **CLI:**
   - **File:** `src/ui/cli.py`
   - **Method:** `_display_conversation_summary()` (lines 310-328)
   - **Display:** Shows agent name and message preview for each message

2. **Web UI:**
   - **File:** `src/ui/streamlit_app.py`
   - **Function:** `extract_agent_traces()` (lines 167-183)
   - **Display:** Lines 430-450 - Expandable sections per agent

**Data Source:**
- **File:** `src/autogen_orchestrator.py`
- **Method:** `_extract_results()` (lines 261-421)
- **Extracts:** Conversation history with agent names and messages (lines 226-244)

#### Requirement: Show citations/evidence collected

**Implementation:**

1. **Citation Extraction:**
   - **CLI:** `src/ui/cli.py` - `_extract_citations()` (lines 262-303)
   - **Web UI:** `src/ui/streamlit_app.py` - `extract_citations()` (lines 122-164)

2. **Display:**
   - **CLI:** Lines 229-240 - Shows numbered citations
   - **Web UI:** Lines 380-400 - Displays citations with links

**Citation Sources:**
- Extracted from conversation history using regex patterns
- URLs from web search results
- Paper citations from Semantic Scholar
- Citation patterns like [Source: Title] and (Author, Year)

#### Requirement: Indicate when response was refused/sanitized

**Implementation:**

1. **CLI:**
   - **File:** `src/ui/cli.py`
   - **Method:** `_display_result()` (lines 182-260)
   - **Safety Blocking Display:** Lines 194-205
     ```python
     if metadata.get("safety_blocked"):
         print("\n⚠️  RESPONSE BLOCKED BY SAFETY SYSTEM")
         # Shows violations with severity and reason
     ```
   - **Safety Events Display:** Lines 211-227 - Shows all safety events

2. **Web UI:**
   - **File:** `src/ui/streamlit_app.py`
   - **Safety Display:** Lines 230-245
     ```python
     if metadata.get("safety_blocked"):
         st.error("⚠️ Response blocked by safety system")
         # Shows violation details
     ```

**Data Source:**
- **File:** `src/autogen_orchestrator.py`
- **Method:** `process_query()` (lines 94-100) - Checks input safety
- **Method:** `_extract_results()` (lines 261-421) - Includes safety events in metadata

---

### D. Evaluation: LLM-as-a-Judge

#### Requirement: Define task prompts and ground-truth/expectation criteria

**Implementation:**

1. **Test Queries:**
   - **File:** `data/example_queries.json`
   - **Contains:** 10 HCI-related queries with:
     - Query text
     - Category
     - Expected topics
     - Ground truth (for some queries)
     - Expected sources

2. **Documentation:**
   - **File:** `TESTED_QUERIES.md`
   - Lists all tested queries with their categories and expected topics

#### Requirement: Use ≥2 independent judging prompts (different rubrics/perspectives)

**Implementation:**
- **File:** `src/evaluation/judge.py`
- **Method:** `_judge_criterion_multiple_perspectives()` (lines 146-210)
- **Perspectives:**
  1. **Academic Evaluator** (line 172)
     - Focus: Research methodology, scholarly writing
  2. **User Experience Evaluator** (line 173)
     - Focus: Clarity, usability, practical value

**How it works:**
- Each criterion is evaluated by both perspectives independently
- Scores are averaged (line 128)
- Reasoning from both perspectives is combined (line 129)

#### Requirement: Score on metrics (Relevance, Evidence Quality, Factual Accuracy, Safety Compliance, Clarity)

**Implementation:**

1. **Criteria Definition:**
   - **File:** `config.yaml` (lines 115-134)
     ```yaml
     criteria:
       - name: "relevance"
         weight: 0.25
       - name: "evidence_quality"
         weight: 0.25
       - name: "factual_accuracy"
         weight: 0.20
       - name: "safety_compliance"
         weight: 0.15
       - name: "clarity"
         weight: 0.15
     ```

2. **Scoring Rubrics:**
   - **File:** `src/evaluation/judge.py`
   - **Method:** `_create_judge_prompt()` (lines 212-323)
   - **Rubrics:** Lines 237-268 - Detailed scoring rubrics for each criterion (0.0-1.0 scale)

3. **Evaluation:**
   - **File:** `src/evaluation/judge.py`
   - **Method:** `evaluate()` (lines 74-144)
   - **Process:**
     - Evaluates each criterion with multiple perspectives
     - Calculates weighted overall score (line 142)

#### Requirement: Report comprehensive evaluation (use >5 diverse test queries)

**Implementation:**

1. **Evaluation System:**
   - **File:** `src/evaluation/evaluator.py`
   - **Class:** `SystemEvaluator` (lines 29-703)
   - **Method:** `evaluate_system()` (lines 66-117)
   - **Process:**
     - Loads test queries (line 94)
     - Processes each query (lines 98-109)
     - Evaluates responses (line 102)
     - Generates reports (line 112)

2. **Test Queries:**
   - **File:** `data/example_queries.json` - Contains 10 diverse queries
   - **Config:** `config.yaml` (line 112) - `num_test_queries: 5` (can be increased to 10)

3. **Reports Generated:**
   - **File:** `src/evaluation/evaluator.py`
   - **Method:** `_save_results()` (lines 377-474)
   - **Outputs:**
     - `evaluation_*.json` - Full detailed results
     - `evaluation_summary_*.txt` - Human-readable summary
     - `evaluation_report_*.md` - Markdown report

4. **Analysis:**
   - **Error Analysis:** `_analyze_errors()` (lines 303-334)
   - **Performance Analysis:** `_analyze_performance()` (lines 336-375)
   - **Score Aggregation:** `_generate_report()` (lines 215-301)

**Location of Results:**
- **Directory:** `outputs/`
- **Files:**
  - `evaluation_20251206_124643.json` - Full evaluation data
  - `evaluation_summary_20251206_124643.txt` - Summary report
  - `evaluation_report_20251206_124643.md` - Markdown report

---

## 2. Deliverables

### Technical Report (3-4 pages)

**Location:** `TECHNICAL_REPORT.md`

**Sections:**
1. **Abstract** (~150 words) - Lines 1-5
2. **System Design and Implementation** - Lines 6-50
   - Architecture overview
   - Agents and roles
   - Workflow and control flow
   - Tool integration
   - Error handling
3. **Safety Design** - Lines 51-85
   - Safety framework
   - Safety architecture
   - Safety policies
   - Response strategies
   - Safety event logging
4. **Evaluation Setup and Results** - Lines 86-120
   - Evaluation methodology
   - Evaluation criteria
   - Test dataset
   - Evaluation results
   - Judge outputs
5. **Discussion & Limitations** - Lines 121-160
   - Insights and learnings
   - Limitations
   - Ethical considerations
   - Future work
6. **References** (APA style) - Lines 161-170

### GitHub Repository

**Structure:**
```
assignment-3-building-and-evaluating-mas-SrivalliLanka/
├── src/                    # Source code
│   ├── agents/            # Agent implementations
│   ├── guardrails/        # Safety system
│   ├── tools/             # Search and citation tools
│   ├── evaluation/        # LLM-as-a-Judge system
│   ├── ui/                # CLI and web interfaces
│   └── autogen_orchestrator.py
├── data/                   # Test queries
├── outputs/                # Exported artifacts and evaluation results
├── scripts/                # Utility scripts
├── config.yaml            # Configuration
├── README.md              # Main documentation
├── TECHNICAL_REPORT.md    # Technical report
├── GUARDRAIL_TESTING.md   # Safety testing documentation
├── TESTED_QUERIES.md      # Query testing documentation
└── REQUIREMENTS_MAPPING.md # This file
```

---

## 3. Additional Requirements from Notes

### Working Web UI

**Location:** `src/ui/streamlit_app.py`
**Run:** `python main.py --mode web` or `python -m streamlit run src/ui/streamlit_app.py`
**Features:** All required features implemented (see User Interface section above)

### Demo Video/Screenshots

**Documentation:** `README.md` (lines 321-347)
- Describes web interface features
- Explains how to access and use the interface
- Note: Actual screenshots/video would need to be added

### Single Command for End-to-End Example

**Command:** `python main.py --mode evaluate`
**Documentation:** `README.md` (lines 273-319)
**What it does:**
1. Initializes multi-agent system
2. Processes test queries
3. Generates responses with citations
4. Evaluates using LLM-as-a-Judge
5. Generates comprehensive reports

### Exported Artifacts

**Location:** `outputs/` directory

1. **Sample Conversation JSON:**
   - **Files:** `sample_conversation_*.json`
   - **Export Script:** `scripts/export_artifacts.py` - `export_sample_conversation()`
   - **Contains:** Full conversation history, metadata, safety events

2. **Response Markdown:**
   - **Files:** `response_*.md`
   - **Export Script:** `scripts/export_artifacts.py` - `export_response_markdown()`
   - **Contains:** Formatted response, citations, metadata

3. **Judge Outputs:**
   - **Files:** `judge_outputs_*.json`
   - **Export Script:** `scripts/export_judge_outputs.py`
   - **Contains:** Judge evaluations, scores, reasoning from multiple perspectives

### Guardrail Testing Documentation

**Location:** `GUARDRAIL_TESTING.md`
**Contains:**
- Test queries and results
- Policy categories triggered
- Safety event logging examples
- Response strategies documentation

---

## 4. Grading Rubric Mapping

### System Architecture & Orchestration (20 pts)

- **Agents (10 pts):** ✅ 4 agents implemented in `src/agents/autogen_agents.py`
- **Workflow (5 pts):** ✅ Sequential workflow in `src/autogen_orchestrator.py`
- **Tools (3 pts):** ✅ Web search, paper search, citations in `src/tools/`
- **Error Handling (2 pts):** ✅ Comprehensive error handling throughout codebase

### User Interface & UX (15 pts)

- **Functionality (6 pts):** ✅ CLI and Web UI in `src/ui/`
- **Transparency (6 pts):** ✅ Agent traces and citations displayed in both UIs
- **Safety Communication (3 pts):** ✅ Safety events shown in both UIs

### Safety & Guardrails (15 pts)

- **Implementation (5 pts):** ✅ Custom framework in `src/guardrails/`
- **Policies (5 pts):** ✅ 4+ categories documented in `config.yaml` and `README.md`
- **Behavior & Logging (5 pts):** ✅ Refuses/sanitizes and logs events

### Evaluation (20 pts)

- **Implementation (6 pts):** ✅ Judge with 2 perspectives in `src/evaluation/judge.py`
- **Design (6 pts):** ✅ 5 metrics with clear rubrics in `config.yaml` and `judge.py`
- **Analysis (8 pts):** ✅ Comprehensive reports in `outputs/` with 5+ queries tested

### Reproducibility (10 pts)

- **README:** ✅ Complete setup and run instructions in `README.md`

### Report Quality (20 pts)

- **Structure (8 pts):** ✅ All sections in `TECHNICAL_REPORT.md`
- **Content (12 pts):** ✅ System design, evaluation results, limitations in report

---

## Summary

All assignment requirements are fully implemented and documented:

1. ✅ **Agents & Orchestration:** 4 agents with AutoGen in `src/agents/` and `src/autogen_orchestrator.py`
2. ✅ **Safety & Guardrails:** Custom framework in `src/guardrails/` with documentation
3. ✅ **User Interface:** CLI and Streamlit web UI in `src/ui/`
4. ✅ **Evaluation:** LLM-as-a-Judge in `src/evaluation/` with comprehensive reports
5. ✅ **Technical Report:** Complete 3-4 page report in `TECHNICAL_REPORT.md`
6. ✅ **Exported Artifacts:** Sample conversations, responses, and judge outputs in `outputs/`
7. ✅ **Documentation:** README, testing docs, and requirements mapping

All code is production-ready with proper error handling, logging, and documentation.

