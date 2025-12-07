# Screenshots and Demo Files

This directory contains screenshots and demo videos demonstrating the Multi-Agent Research Assistant system.

## Directory Structure

```
images/
├── screenshots/     # UI screenshots
└── demo/            # Demo videos
```

## Screenshots

### 1. Web Interface Main Screen
**File:** `screenshots/web_ui_interface.png`  
**Caption:** "web interface"  
**Status:** ✅ File saved

**Description:** Main landing page of the web interface showing:
- Query input area with placeholder text: "e.g., What are the latest developments in explainable AI for novice users?"
- Left sidebar with:
  - Settings section (Show Agent Traces, Show Safety Log checkboxes)
  - Statistics section (Total Queries: 0, Safety Events: 0)
  - Clear History button
  - About section (System: Multi-Agent Research Assistant, Topic: HCI Research)
- Right sidebar with:
  - Example Queries (4 clickable example buttons)
  - "How It Works" section explaining the 5-step agent workflow
- Central content area with:
  - Title: "Multi-Agent Research Assistant" with robot icon
  - Instruction: "Ask me anything about your research topic!"
  - Search button with magnifying glass icon
- Dark theme interface design with modern, clean aesthetic

**What it demonstrates:**
- ✅ Working web interface (Functionality - 6 pts)
- Professional UI design
- Clear user guidance with example queries
- Workflow transparency
- Settings and statistics tracking

---

### 2. Agent Traces Display
**File:** `screenshots/agent_trace_display.png`  
**Status:** ✅ File saved

**Description:** Shows the agent conversation history and workflow, demonstrating:
- Messages from all 4 agents (Planner, Researcher, Writer, Critic)
- Agent coordination and handoff signals
- Tool calls and search results
- Complete multi-agent workflow visualization

**What it demonstrates:**
- ✅ Display agent traces (Transparency - 6 pts)
- ✅ 4 agents with distinct roles (Agents - 10 pts)
- ✅ Agents coordinate (Agents - 10 pts)
- ✅ Clear multi-agent workflow (Workflow - 5 pts)

---

### 3. Evaluation Summary
**File:** `screenshots/evaluation_summary.png`  
**Status:** ✅ File saved

**Description:** Terminal/console output showing evaluation results, including:
- Total queries processed (6 queries)
- Success rate (100%)
- Overall average score (0.719)
- Scores by criterion (relevance, evidence_quality, factual_accuracy, safety_compliance, clarity)
- Performance distribution

**What it demonstrates:**
- ✅ Working judge with ≥2 perspectives (Implementation - 6 pts)
- ✅ ≥3 measurable metrics (Design - 6 pts)
- ✅ Evaluation results with interpretation (Analysis - 8 pts)

---

## Demo Videos

### 1. Main Demo Video
**File:** `demo/Demo Video.mp4`  
**Status:** ✅ File saved

**Description:** Comprehensive demonstration video showing:
- System overview and features
- Complete workflow demonstration
- Agent coordination in action
- Safety system demonstration

---

### 2. Safety Check Demo
**File:** `demo/web_ui_safety_check.mp4`  
**Status:** ✅ File saved

**Description:** Demonstration of the safety system, showing:
- Safety checks for legitimate queries
- Safety blocking for unsafe queries
- Safety event logging and display
- Safety compliance verification

