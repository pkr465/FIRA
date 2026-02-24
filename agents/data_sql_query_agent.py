"""
FIRA SQL Query Agent — Comprehensive, Interactive, Smart

Features:
  - Query validation & disambiguation before SQL generation
  - Suggested corrections for suboptimal queries
  - Auto-retry with self-healing SQL
  - Post-execution LLM analysis: trends, insights, anomalies
  - Follow-up question suggestions
  - Data quality warnings
  - Confidence scoring
"""

import json
import logging
from typing import Dict, List, Any, Tuple, Optional

# Import the centralized schema configuration
try:
    from config.schema_config import SCHEMA_CONFIG
except ImportError:
    SCHEMA_CONFIG = {}

# Import Database Utility
try:
    from utils.models.database import OpexDB
except ImportError:
    class OpexDB:
        @staticmethod
        def execute_sql_query(sql, format_as_markdown=False):
            raise ImportError("OpexDB not found")

# Import Database Session
try:
    from utils.models.database import get_db_session
except ImportError:
    def get_db_session(): yield None

# Import Agent Utils
try:
    from agents.utils.agent_utils import AgentUtils
except ImportError:
    try:
        from agent_utils import AgentUtils
    except ImportError:
        pass

try:
    from config.labeling import QuerySchemaMapper
except ImportError:
    class QuerySchemaMapper:
        def get_relevant_schema_context(self, query):
            return ""

logger = logging.getLogger(__name__)

# ==============================================================================
# RICH SCHEMA DEFINITIONS
# ==============================================================================

LABELS_CONTEXT = """
### DETAILED COLUMN DEFINITIONS & MAPPING

You have access to THREE tables. Choose the right one(s) based on the user's question.

---
#### TABLE 1: `opex_data_hybrid`  (OpEx Financial Data)
Contains a JSONB column named `additional_data`. Most business columns are INSIDE this JSON.

1. **METRICS (Effort/Cost)**
   - "Spend", "Cost", "Actual" (DOLLARS) -> `ods_m` column (or `CAST(additional_data->>'ods_m' AS NUMERIC)`)
   - "Budget", "TM1" (DOLLARS) -> `tm1_m` column (or `CAST(additional_data->>'tm1_m' AS NUMERIC)`)
   - "Man-months", "MM", "Headcount" -> `ods_mm` column (or `CAST(additional_data->>'ods_mm' AS NUMERIC)`)
   - "Budget MM", "Plan MM" -> `tm1_mm` column (or `CAST(additional_data->>'tm1_mm' AS NUMERIC)`)

2. **GEOGRAPHY**
   - "Country", "Region" -> `additional_data->>'home_dept_region_r1'`
   - "City", "Location" -> `additional_data->>'home_dept_region_r2'`

3. **PEOPLE**
   - "VP" -> `additional_data->>'dept_vp'`
   - "Lead" -> `additional_data->>'dept_lead'`

4. **TIME**
   - "Year" -> `additional_data->>'fiscal_year'`
   - "Quarter" -> `additional_data->>'fiscal_quarter'`

5. **PROJECT**
   - "Project" -> `additional_data->>'project_desc'`
   - "HW/SW" -> `additional_data->>'hw_sw'`

6. **DATA TYPE FILTER & COLUMN SELECTION** (IMPORTANT):
   - For dollar/spend queries: use `ods_m` (actual) and `tm1_m` (budget), filter `COALESCE(data_type, 'dollar') = 'dollar'`
   - For man-month/HC queries: use `ods_mm` (actual) and `tm1_mm` (budget), filter `COALESCE(data_type, 'dollar') = 'mm'`
   - NEVER use `ods_mm` for dollar queries or `ods_m` for man-month queries

---
#### TABLE 2: `bpafg_demand`  (Resource Planner — Demand)
Standard relational columns (NO JSON needed):
- `resource_name` TEXT — person / resource name
- `project_name` TEXT — project
- `task_name` TEXT — task
- `homegroup` TEXT — team / group
- `resource_security_group` TEXT
- `primary_bl` TEXT — business line
- `dept_country` TEXT — country
- `demand_type` TEXT — e.g. "Plan", "Actual"
- `month` TEXT — month key (e.g. "2025-01", "Jan-25")
- `value` NUMERIC — headcount / FTE value
- `source_file` TEXT

Use this table for: headcount demand, resource allocation by project,
staffing, FTE, demand planning, resource by country, team capacity.

---
#### TABLE 3: `priority_template`  (Resource Planner — Priority & Capacity)
Standard relational columns (NO JSON needed):
- `project` TEXT — project name
- `priority` INTEGER — priority ranking (1 = highest)
- `country` TEXT
- `target_capacity` NUMERIC
- `country_cost` NUMERIC — cost per resource in that country
- `month` TEXT
- `monthly_capacity` NUMERIC
- `source_file` TEXT

Use this table for: project priority, country capacity,
resource cost by country, priority ranking.

---
#### CROSS-TABLE TIPS:
- To combine OpEx spend with demand data, JOIN `opex_data_hybrid` and `bpafg_demand`
  on project (e.g., `additional_data->>'project_desc' = bpafg_demand.project_name`).
- To combine demand with priority, JOIN `bpafg_demand.project_name = priority_template.project`.
"""

SQL_QUERY_PROMPT = """
You are a PostgreSQL expert specialized in Financial and Resource Planning data.
Your task is to generate an executable SQL query against one or more tables:
  - `opex_data_hybrid` (OpEx financials — uses JSONB `additional_data` column)
  - `bpafg_demand` (resource demand — standard relational columns)
  - `priority_template` (project priority & capacity — standard relational columns)

### CRITICAL RULES (DO NOT IGNORE):
1. **NO BIND PARAMETERS**:
   - You **MUST NOT** use placeholders like `:value`, `?`, or `%s`.
   - You **MUST** inject the literal values directly into the SQL string.
   - WRONG: `WHERE additional_data->>'fiscal_year' = :fiscal_year`
   - CORRECT: `WHERE additional_data->>'fiscal_year' = '2025'`

2. **JSON Extraction (opex_data_hybrid ONLY)**:
   - Use `additional_data->>'key_name'` for business fields in `opex_data_hybrid`.
   - Text matching should be case-insensitive using `ILIKE`.
   - For `bpafg_demand` and `priority_template` use regular column names directly.

3. **Data Types**:
   - `ods_mm` is text in JSON. You MUST cast: `CAST(additional_data->>'ods_mm' AS NUMERIC)`.
   - Handle NULLs: `COALESCE(CAST(... AS NUMERIC), 0)`.
   - Columns in `bpafg_demand` and `priority_template` are already typed — no JSON needed.

4. **UNION Sorting**:
   - If using `UNION`, the `ORDER BY` clause MUST refer to column names or indices, NOT expressions.

5. **DATA TYPE FILTERING (opex_data_hybrid)**:
   - For dollar/spend queries: always add `AND COALESCE(data_type, 'dollar') = 'dollar'`
   - For man-month/headcount queries: always add `AND COALESCE(data_type, 'dollar') = 'mm'`

### RESPONSE FORMAT:
Return a JSON object with these keys:
{{
    "sql": "SELECT ...",
    "explanation": "A professional, executive-level explanation of the analysis (2-4 sentences). Describe what the query measures, which table(s) are being queried, and what business insight the results provide. Use clear financial/resource planning terminology suitable for senior leadership.",
    "chart_type": "bar|grouped_bar|line|pie|area|scatter|heatmap|treemap|waterfall|none"
}}

### CHART TYPE SELECTION:
Choose `chart_type` based on the data and user's intent:
- "bar" — single metric comparison across categories (default for most queries)
- "grouped_bar" — comparing 2+ metrics side-by-side (e.g., budget vs actual)
- "line" — time-series trends (monthly, quarterly data over time)
- "pie" — composition/share analysis (e.g., "breakdown", "distribution", "share")
- "area" — cumulative time-series (stacked trends)
- "scatter" — correlation between two metrics
- "heatmap" — 2D matrix comparisons (country × quarter, etc.)
- "treemap" — hierarchical composition (e.g., VP → project → spend)
- "waterfall" — variance/delta analysis (budget vs actual changes)
- "none" — when visualization doesn't add value (simple counts, single values)

If the user explicitly requests a chart type (e.g., "show me a pie chart", "plot a line trend"), use that type.
If the user says "plot", "chart", "visualize", "graph", pick the most appropriate type for the data.
"""

SQL_QUERY_FIX_PROMPT = """
The previous SQL query failed.
Please fix it based on the error.

# Broken Query:
{sql}

# Error Message:
{error_msg}

# FIX INSTRUCTIONS:
1. **Bind Parameter Error?** (e.g. "value required for bind parameter")
   - You likely used `:param` or `%s`. REPLACE them with exact literal values (e.g. '2025').
2. **UNION Order Error?**
   - Simplify the ORDER BY clause. Sort by column name only.
3. **Column Error?**
   - Check if you forgot `additional_data->>`.
4. **Type Error?**
   - Ensure numeric casts with COALESCE.

Return the fixed query in JSON format:
{{"sql": "...", "explanation": "..."}}
"""

# ==============================================================================
# QUERY VALIDATION & DISAMBIGUATION
# ==============================================================================

QUERY_VALIDATION_PROMPT = """
You are a query quality analyst for a financial database system. Analyze the user's query and determine if it is clear enough to generate accurate SQL.

**Available Data:**
{schema_hint}

**User Query:** "{user_query}"

**Evaluate:**
1. Is the query specific enough? (does it mention what metric, time period, grouping?)
2. Are there ambiguous terms that could map to multiple columns?
3. Is the query asking for something the database can actually answer?
4. Could the query be improved for better results?

**Return JSON:**
{{
    "is_clear": true/false,
    "confidence": 0.0 to 1.0,
    "issues": ["list of ambiguity issues, if any"],
    "suggestions": ["list of improved query phrasings, if any"],
    "clarifying_questions": ["questions to ask the user, if needed"],
    "interpreted_as": "How you understand the query in precise terms"
}}
"""

# ==============================================================================
# POST-EXECUTION ANALYSIS
# ==============================================================================

INSIGHT_ANALYSIS_PROMPT = """
You are a Senior Financial & Resource Planning Analyst presenting findings to C-level executives.

**Original Question:** {user_question}
**SQL Query Executed:** {sql}
**Query Explanation:** {explanation}
**Data Results:**
{results}

**Your Task — Provide a comprehensive analysis:**

1. **Executive Summary** (2-3 sentences): What does the data tell us? Summarize the key finding.

2. **Key Metrics**: Identify the most important numbers and their significance.

3. **Trends & Patterns**: Are there any notable trends, patterns, or seasonality in the data?
   - Year-over-year changes
   - Quarter-over-quarter trends
   - Concentration patterns (e.g., top 3 items represent X% of total)

4. **Anomalies & Outliers**: Flag anything unusual — unexpectedly high/low values, missing data gaps, sudden changes.

5. **Variance Analysis**: If budget vs actual data is present, analyze the variance (favorable/unfavorable).

6. **Actionable Insights**: Based on the data, what should leadership consider or investigate further?

7. **Data Quality Notes**: Flag any data quality concerns (nulls, negative values, inconsistencies).

**Format your response in clear, professional prose suitable for an executive briefing. Use precise dollar amounts and percentages. Do NOT repeat the raw data table — synthesize insights from it.**
"""

FOLLOWUP_SUGGESTIONS_PROMPT = """
Based on the user's question and the data results, suggest 3 natural follow-up questions that would deepen their analysis.

**Original Question:** {user_question}
**Data Summary:** {data_summary}

**Guidelines:**
- Make suggestions specific and actionable (not generic)
- Each suggestion should explore a different angle: drill-down, comparison, trend, or root-cause
- Phrase them as natural questions the user would actually ask
- Include the time period, metric, or dimension they should investigate

**Return JSON list:**
["question 1", "question 2", "question 3"]
"""


class SQLQueryAgent:
    def __init__(self, tools=None):
        self.schema_config = SCHEMA_CONFIG
        self.table_name = self.schema_config.get("table_name", "opex_data_hybrid")
        self.tools = tools if tools else AgentUtils()
        self.schema_mapper = QuerySchemaMapper()

    def get_schema_context(self) -> str:
        schema_sql = self.schema_config.get("create_table_sql", "")
        labels_context = LABELS_CONTEXT.format(table_name=self.table_name)
        return f"{schema_sql}\n\n{labels_context}"

    # ==================================================================
    # STEP 1: Query Validation & Disambiguation
    # ==================================================================

    def validate_query(self, user_query: str) -> Dict[str, Any]:
        """
        Validates the user query before SQL generation.
        Returns validation result with suggestions if the query is suboptimal.
        """
        try:
            schema_hint = LABELS_CONTEXT.format(table_name=self.table_name)
            prompt = QUERY_VALIDATION_PROMPT.format(
                schema_hint=schema_hint,
                user_query=user_query,
            )
            resp = self.tools.llm_call(prompt)
            cleaned = resp.strip().replace("```json", "").replace("```", "")
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                return json.loads(cleaned[start:end + 1])
        except Exception as e:
            logger.warning(f"Query validation failed: {e}")

        # Default: proceed with query as-is
        return {
            "is_clear": True,
            "confidence": 0.7,
            "issues": [],
            "suggestions": [],
            "clarifying_questions": [],
            "interpreted_as": user_query,
        }

    # ==================================================================
    # STEP 2: SQL Generation
    # ==================================================================

    def _llm_sql_gen(self, prompt: str) -> Tuple[str, str, str]:
        """Returns (sql, explanation, chart_type)."""
        logger.info("Generating SQL with LLM...")
        try:
            resp = self.tools.llm_call(prompt)
            if not isinstance(resp, str):
                return "", "LLM Error: Non-string response", "bar"

            cleaned_resp = resp.strip().replace("```json", "").replace("```", "")
            resp_obj = json.loads(cleaned_resp)
            return (
                resp_obj.get("sql", ""),
                resp_obj.get("explanation", ""),
                resp_obj.get("chart_type", "bar"),
            )

        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON: {resp}")
            return "", "JSON Parsing Error", "bar"
        except Exception as e:
            logger.error(f"Error processing LLM: {e}")
            return "", f"Error: {str(e)}", "bar"

    def get_sql(self, query_text: str) -> Tuple[str, str, str]:
        """Returns (sql, explanation, chart_type)."""
        try:
            system_prompt = SQL_QUERY_PROMPT.format(table_name=self.table_name)
        except KeyError:
            return "", "Prompt error", "bar"

        schema_context = self.get_schema_context()
        relevant_context = self.schema_mapper.get_relevant_schema_context(query_text)

        prompt = (
            f"{system_prompt}\n\n"
            f"### Schema:\n{schema_context}\n\n"
            f"### Context:\n{relevant_context}\n\n"
            f"### User Request:\n{query_text}\n"
        )

        return self._llm_sql_gen(prompt)

    def fix_sql(self, sql: str, explanation: str, error_msg: str) -> str:
        try:
            prompt = SQL_QUERY_FIX_PROMPT.format(
                sql=sql,
                error_msg=error_msg,
                explanation=explanation,
            )
            sql, _, _ = self._llm_sql_gen(prompt)
            return sql
        except Exception as e:
            logger.error(f"Fix prompt error: {e}")
            return ""

    # ==================================================================
    # STEP 3: Execution
    # ==================================================================

    def execute_query(self, sql: str) -> Any:
        if not sql:
            return None
        logger.info(f"Executing SQL: {sql}")
        try:
            results = OpexDB.execute_sql_query(sql, format_as_markdown=True)
            return results
        except Exception as e:
            # Attempt rollback
            try:
                session_gen = get_db_session()
                session = next(session_gen)
                if session:
                    session.rollback()
                    logger.info("Database session rolled back successfully.")
            except Exception as rollback_err:
                logger.warning(f"Failed to rollback session: {rollback_err}")

            logger.error(f"DB Error: {e}")
            raise e

    # ==================================================================
    # STEP 4: Post-Execution Insight Analysis
    # ==================================================================

    def _deep_analysis(self, user_input: str, sql: str, explanation: str, results: Any) -> str:
        """Generate comprehensive LLM analysis with trends, anomalies, and insights."""
        try:
            results_text = str(results)[:3000] if results else "No results returned."
            prompt = INSIGHT_ANALYSIS_PROMPT.format(
                user_question=user_input,
                sql=sql,
                explanation=explanation,
                results=results_text,
            )
            return self.tools.llm_call(prompt)
        except Exception as e:
            logger.warning(f"Deep analysis generation failed: {e}")
            return explanation

    def _generate_followups(self, user_input: str, results: Any) -> List[str]:
        """Generate contextual follow-up question suggestions."""
        try:
            data_summary = str(results)[:1500] if results else "No data"
            prompt = FOLLOWUP_SUGGESTIONS_PROMPT.format(
                user_question=user_input,
                data_summary=data_summary,
            )
            resp = self.tools.llm_call(prompt)
            cleaned = resp.strip().replace("```json", "").replace("```", "")
            start = cleaned.find("[")
            end = cleaned.rfind("]")
            if start != -1 and end != -1:
                suggestions = json.loads(cleaned[start:end + 1])
                return suggestions[:3]
        except Exception as e:
            logger.warning(f"Follow-up generation failed: {e}")
        return []

    def _check_data_quality(self, results: Any) -> List[str]:
        """Quick heuristic checks on results for data quality warnings."""
        warnings = []
        if results is None:
            return ["No results returned — the query may be too restrictive or the table may be empty."]

        results_str = str(results)

        if "None" in results_str or "null" in results_str.lower():
            warnings.append("Some values contain NULL/None — data may be incomplete for certain records.")

        if results_str.count("\n") <= 2:
            warnings.append("Very few rows returned — consider broadening your query filters.")

        if "0.00" in results_str:
            count_zeros = results_str.count("0.00")
            if count_zeros > 3:
                warnings.append(f"Multiple zero values detected ({count_zeros} instances) — verify data completeness.")

        # Check for negative values in financial context
        if "-" in results_str and any(kw in results_str.lower() for kw in ["spend", "budget", "cost"]):
            warnings.append("Negative financial values detected — this may indicate credits, reversals, or data issues.")

        return warnings

    # ==================================================================
    # MAIN RUN METHOD
    # ==================================================================

    def run(self, user_input: str, retry_limit: int = 3) -> Dict[str, Any]:
        """
        Full pipeline:
        1. Validate query → provide suggestions if suboptimal
        2. Generate SQL
        3. Execute with retry + auto-fix
        4. Deep LLM analysis on results
        5. Generate follow-up suggestions
        6. Data quality checks
        """

        # Step 1: Validate
        validation = self.validate_query(user_input)
        logger.info(f"Validation: clear={validation.get('is_clear')}, confidence={validation.get('confidence')}")

        # If query is too ambiguous and we have clarifying questions, return them
        if (
            not validation.get("is_clear", True)
            and validation.get("confidence", 1.0) < 0.5
            and validation.get("clarifying_questions")
        ):
            return {
                "status": "clarification_needed",
                "message": "I'd like to clarify your request to give you the most accurate results.",
                "interpreted_as": validation.get("interpreted_as", ""),
                "issues": validation.get("issues", []),
                "clarifying_questions": validation.get("clarifying_questions", []),
                "suggestions": validation.get("suggestions", []),
            }

        # Step 2: Generate SQL
        sql, explanation, chart_type = self.get_sql(user_input)
        if not sql:
            return {
                "status": "error",
                "message": "I wasn't able to generate a SQL query for that request. Could you rephrase it?",
                "suggestions": validation.get("suggestions", []),
            }

        # Step 3: Execute with retry
        current_try = 0
        last_error = ""
        while current_try < retry_limit:
            try:
                results = self.execute_query(sql)

                # Step 4: Deep analysis
                analysis = self._deep_analysis(user_input, sql, explanation, results)

                # Step 5: Follow-up suggestions
                followups = self._generate_followups(user_input, results)

                # Step 6: Data quality
                dq_warnings = self._check_data_quality(results)

                return {
                    "status": "success",
                    "sql": sql,
                    "explanation": analysis,
                    "results": results,
                    "chart_type": chart_type,
                    "followup_suggestions": followups,
                    "data_quality_warnings": dq_warnings,
                    "query_interpretation": validation.get("interpreted_as", ""),
                    "validation_suggestions": validation.get("suggestions", []),
                }
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Attempt {current_try + 1} failed: {e}")
                sql = self.fix_sql(sql, explanation, last_error)
                current_try += 1

        return {
            "status": "error",
            "message": (
                f"I tried {retry_limit} times but couldn't execute the query successfully. "
                f"Last error: {last_error[:200]}"
            ),
            "last_sql": sql,
            "suggestions": validation.get("suggestions", [
                "Try rephrasing your question with specific column names",
                "Specify the time period (e.g., 'in FY2025')",
                "Mention the exact table: OpEx spend, resource demand, or project priority",
            ]),
        }
