# Tested Queries Documentation

This document lists the queries from `data/example_queries.json` that were tested during evaluation.

## Evaluation Configuration

- **Total Queries in Dataset:** 10
- **Queries Tested:** 5 (reduced for faster evaluation, configurable in `config.yaml`)
- **Evaluation Date:** 2025-12-06
- **Evaluation Mode:** Full system evaluation with LLM-as-a-Judge

## Tested Queries

### Query 1: Explainable AI for Novices
**Query:** "What are the key principles of explainable AI for novice users?"
**Category:** `explainable_ai`
**Ground Truth:** "Explainable AI for novices should focus on transparency, simple visualizations, interactive explanations, and building user trust through understandable model behavior."
**Status:** ✅ Tested
**Expected Topics:** transparency, interpretability, user understanding, trust

### Query 2: AR Usability Evolution
**Query:** "How has AR usability evolved in the past 5 years?"
**Category:** `ar_usability`
**Ground Truth:** "AR usability has evolved significantly with improved hand tracking, spatial mapping, gesture recognition, and more intuitive interaction paradigms. Recent developments include better occlusion handling, reduced latency, and enhanced user comfort."
**Status:** ✅ Tested
**Expected Topics:** interaction techniques, user experience, hardware improvements, application domains

### Query 3: AI Ethics in Education
**Query:** "What are ethical considerations in using AI for education?"
**Category:** `ai_ethics`
**Ground Truth:** "Key ethical considerations include algorithmic bias and fairness, student data privacy, transparency in AI decision-making, accessibility for all learners, maintaining student autonomy, and ensuring equitable access to AI-enhanced educational tools."
**Status:** ✅ Tested
**Expected Topics:** bias, privacy, transparency, accessibility, student autonomy

### Query 4: UX Measurement Approaches
**Query:** "Compare different approaches to measuring user experience in mobile applications"
**Category:** `ux_measurement`
**Ground Truth:** null (comparative query)
**Status:** ✅ Tested
**Expected Topics:** questionnaires, analytics, user testing, physiological measures

### Query 5: Conversational AI in Healthcare
**Query:** "What are the latest developments in conversational AI for healthcare?"
**Category:** `conversational_ai`
**Ground Truth:** null
**Status:** ✅ Tested
**Expected Topics:** chatbots, patient interaction, clinical decision support, privacy concerns

## Additional Queries in Dataset (Not Tested in This Run)

The following queries are available in `data/example_queries.json` but were not tested in this evaluation run:

6. **Accessibility Design Patterns:** "How do design patterns for accessibility differ across web and mobile platforms?"
7. **Uncertainty Visualization:** "What are best practices for visualizing uncertainty in data displays?"
8. **Voice Interfaces for Elderly:** "How can voice interfaces be designed for elderly users?"
9. **AI-Driven Prototyping:** "What are emerging trends in AI-driven prototyping tools?"
10. **Cross-Cultural Design:** "How do cultural factors influence mobile app design?"

## Running Full Evaluation

To test all 10 queries, update `config.yaml`:

```yaml
evaluation:
  num_test_queries: 10  # Change from 5 to 10
```

Then run:
```bash
python main.py --mode evaluate
```

## Evaluation Results

Evaluation results are saved to `outputs/` directory:
- `evaluation_*.json` - Detailed results for all tested queries
- `evaluation_summary_*.txt` - Human-readable summary
- `evaluation_report_*.md` - Markdown report

## Notes

- Queries are selected in order from `data/example_queries.json`
- The system processes each query through the full multi-agent workflow
- Each response is evaluated using LLM-as-a-Judge with two perspectives (Academic and User Experience)
- Evaluation includes scores for: relevance, evidence quality, factual accuracy, safety compliance, and clarity

