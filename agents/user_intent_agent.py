"""
FIRA User Intent Agent — Smart Router with Clarification

Features:
  - LLM-based intent classification with keyword fallback
  - Low-confidence detection → asks clarifying questions
  - Refined query translation (business terms → schema columns)
  - Structured response passthrough from agents (dict or str)
"""

import logging
import json
from typing import Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel

from config.config import Config
from config.schema_config import SCHEMA_CONFIG
from agents.utils.agent_utils import AgentUtils
from agents.data_sql_query_agent import SQLQueryAgent
from agents.semantic_search_agent import SemanticSearchAgent
from agents.chatbot_agent import ChatbotAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    DATA_SQL = "DATA_SQL_QUERY"
    SEMANTIC_RAG = "SEMANTIC_SEARCH"
    GENERAL_CHAT = "GENERAL_CHAT"


class IntentResponse(BaseModel):
    intent: IntentType
    confidence: float
    reasoning: str
    suggested_agent: str
    refined_query: Optional[str] = None


# Condensed Schema Map for Intent Recognition
INTENT_SCHEMA_HINT = """
**Table: opex_data_hybrid** (OpEx Financials — JSONB `additional_data`):
- **Financials**: 'ods_mm' (Spend, Cost, Effort), 'tm1_mm' (Budget)
- **Geography**: 'home_dept_region_r1' (Country), 'home_dept_region_r2' (City/Location)
- **Organization**: 'dept_lead' (Manager), 'dept_vp' (VP), 'home_dept_desc' (Department)
- **Time**: 'fiscal_year', 'fiscal_quarter'
- **Project**: 'project_desc' (Project Name), 'hw_sw' (HW/SW Category)
- **Data Type**: data_type = 'dollar' (spend) or 'mm' (man-months)

**Table: bpafg_demand** (Resource Planner — Demand):
- resource_name, project_name, task_name, homegroup, dept_country
- demand_type, month, value (headcount / FTE)
- Keywords: headcount, demand, staffing, FTE, allocation, resource plan

**Table: priority_template** (Resource Planner — Priority & Capacity):
- project, priority, country, target_capacity, country_cost, month, monthly_capacity
- Keywords: priority, capacity, ranking, cost per resource
"""


class UserIntentAgent:
    def __init__(self):
        self.utils = AgentUtils()
        self.sql_agent = SQLQueryAgent()
        self.semantic_agent = SemanticSearchAgent()
        self.chatbot_agent = ChatbotAgent()

    def identify_intent(self, user_query: str) -> IntentResponse:
        """
        Classifies intent with explicit instruction to map business terms to schema columns.
        """
        logger.info(f"Analyzing intent for query: {user_query}")

        full_prompt = f"""
        You are an intelligent Intent Classifier/Router.
        Your goal is to classify the user's request and, if it is a data question, REFINE it to use correct database terminology.

        --- AVAILABLE DATA TERMS (HINTS) ---
        {INTENT_SCHEMA_HINT}

        --- CATEGORIES ---
        1. **DATA_SQL_QUERY**:
           - User asks for specific facts, numbers, lists, or rankings found in the database.
           - *Crucial*: If the user mentions "Spend", "Headcount", "Location", "Projects", or "Managers", it is likely this category.
           - Also includes Resource Planner questions: "demand", "staffing", "FTE", "capacity", "priority", "allocation by project", "headcount by country".

        2. **SEMANTIC_SEARCH**:
           - User asks for explanations, policies, "How to", or textual summaries of documents.
           - Keywords: "Explain", "Summarize", "Policy", "Meaning of".

        3. **GENERAL_CHAT**:
           - Greetings, general logic, or questions unrelated to the business data.

        --- TASK ---
        Analyze the input: "{user_query}"

        If the intent is DATA_SQL_QUERY, you MUST generate a `refined_query` that translates the user's terms to the hints provided above.
        Example:
        User: "Show me spend by city"
        Refined: "Show me sum(ods_mm) grouped by home_dept_region_r2"

        --- OUTPUT FORMAT (JSON ONLY) ---
        {{
            "intent": "DATA_SQL_QUERY" | "SEMANTIC_SEARCH" | "GENERAL_CHAT",
            "confidence": 0.0 to 1.0,
            "reasoning": "Why?",
            "suggested_agent": "SqlAgent" | "SemanticAgent" | "ChatBot",
            "refined_query": "The translated query if Data SQL, else null"
        }}
        """

        try:
            response_text = self.utils.llm_call(full_prompt)
            cleaned_response = response_text.replace("```json", "").replace("```", "").strip()

            start_idx = cleaned_response.find("{")
            end_idx = cleaned_response.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = cleaned_response[start_idx : end_idx + 1]
                data = json.loads(json_str)
                if not data or "intent" not in data:
                    raise ValueError("LLM returned empty or invalid JSON (possible API error)")
                return IntentResponse(**data)
            else:
                raise ValueError("No JSON found in LLM response")

        except Exception as e:
            logger.warning(f"Intent classification fell back to keyword routing: {e}")
            return self._keyword_fallback(user_query)

    def _keyword_fallback(self, user_query: str) -> IntentResponse:
        """
        Rule-based intent classification when the LLM is unavailable.
        """
        q = user_query.lower()

        sql_keywords = [
            "spend", "budget", "cost", "total", "sum", "average", "count",
            "how much", "how many", "list", "show me", "top", "bottom",
            "compare", "breakdown", "by country", "by project", "by department",
            "headcount", "demand", "fte", "allocation", "capacity", "staffing",
            "priority", "ranking", "trend", "quarterly", "fiscal", "variance",
            "opex", "resource", "department", "manager", "lead", "region",
            "man month", "man-month", "mm",
        ]

        rag_keywords = [
            "explain", "summarize", "what is", "what are", "policy",
            "meaning", "define", "how to", "why", "describe", "overview",
            "documentation", "guide", "process",
        ]

        sql_score = sum(1 for kw in sql_keywords if kw in q)
        rag_score = sum(1 for kw in rag_keywords if kw in q)

        if sql_score >= 2 or (sql_score >= 1 and rag_score == 0 and len(q.split()) > 3):
            return IntentResponse(
                intent=IntentType.DATA_SQL,
                confidence=0.75,
                reasoning="Keyword-based routing (LLM unavailable): data/SQL query detected",
                suggested_agent="SqlAgent",
                refined_query=user_query,
            )
        elif rag_score >= 1:
            return IntentResponse(
                intent=IntentType.SEMANTIC_RAG,
                confidence=0.70,
                reasoning="Keyword-based routing (LLM unavailable): semantic search detected",
                suggested_agent="SemanticAgent",
            )
        else:
            return IntentResponse(
                intent=IntentType.GENERAL_CHAT,
                confidence=0.80,
                reasoning="Keyword-based routing (LLM unavailable): general chat",
                suggested_agent="ChatBot",
            )

    def route_and_execute(self, user_query: str) -> Any:
        """
        Routes the query to the appropriate agent and returns the result.
        Returns can be: str (chat/semantic) or dict (SQL agent structured response).
        """
        decision = self.identify_intent(user_query)
        logger.info(f"Decision: {decision.intent}, Confidence: {decision.confidence}, Refined: {decision.refined_query}")

        # Low confidence — return a clarification response
        if decision.confidence < 0.50:
            return {
                "status": "clarification_needed",
                "message": (
                    f"I'm not fully sure what you're looking for (confidence: {decision.confidence:.0%}). "
                    "Could you be more specific?"
                ),
                "suggestions": [
                    "Try asking about specific metrics: 'total spend by project'",
                    "For resource data: 'headcount demand by country'",
                    "For explanations: 'explain the variance report process'",
                ],
                "reasoning": decision.reasoning,
            }

        if decision.intent == IntentType.DATA_SQL:
            final_query = decision.refined_query if decision.refined_query else user_query
            # SQL agent returns a dict — pass it through directly
            result = self.sql_agent.run(final_query)
            return result

        elif decision.intent == IntentType.SEMANTIC_RAG:
            return self.semantic_agent.run(user_query)

        else:
            return self.chatbot_agent.run(user_query)


if __name__ == "__main__":
    agent = UserIntentAgent()
    print(agent.route_and_execute("What is the spend in San Jose for Q4?"))
