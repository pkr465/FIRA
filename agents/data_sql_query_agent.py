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
   - "Spend", "Cost", "Resources" -> `CAST(additional_data->>'ods_mm' AS NUMERIC)`
   - "Budget", "TM1" -> `CAST(additional_data->>'tm1_mm' AS NUMERIC)`

2. **GEOGRAPHY**
   - "Country", "Region" -> `additional_data->>'home_dept_region_r1'`
   - "City", "Location" -> `additional_data->>'home_dept_region_r2'`

3. **PEOPLE**
   - "VP" -> `additional_data->>'dept_vp'`
   - "Lead" -> `additional_data->>'dept_lead'`

4. **TIME**
   - "Year" -> `additional_data->>'fiscal_year'`
   - "Quarter" -> `additional_data->>'fiscal_quarter'`

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

### RESPONSE FORMAT:
Return a JSON object with two keys:
{{
    "sql": "SELECT ...",
    "explanation": "A professional, executive-level explanation of the analysis (2-4 sentences). Describe what the query measures, which table(s) are being queried, and what business insight the results provide. Use clear financial/resource planning terminology suitable for senior leadership."
}}
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

Return the fixed query in JSON format.
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

    def _llm_sql_gen(self, prompt: str) -> Tuple[str, str]:
        logger.info("Generating SQL with LLM...")
        try:
            resp = self.tools.llm_call(prompt)
            if not isinstance(resp, str):
                return "", "LLM Error: Non-string response"

            cleaned_resp = resp.strip().replace("```json", "").replace("```", "")
            resp_obj = json.loads(cleaned_resp)
            return resp_obj.get("sql", ""), resp_obj.get("explanation", "")
            
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON: {resp}")
            return "", "JSON Parsing Error"
        except Exception as e:
            logger.error(f"Error processing LLM: {e}")
            return "", f"Error: {str(e)}"

    def get_sql(self, query_text: str) -> Tuple[str, str]:
        try:
            system_prompt = SQL_QUERY_PROMPT.format(table_name=self.table_name)
        except KeyError:
            return "", "Prompt error"

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
                explanation=explanation
            )
            sql, _ = self._llm_sql_gen(prompt)
            return sql
        except Exception as e:
            logger.error(f"Fix prompt error: {e}")
            return ""

    def execute_query(self, sql: str) -> Any:
        if not sql:
            return None
        logger.info(f"Executing SQL: {sql}")
        try:
            # We attempt execution
            results = OpexDB.execute_sql_query(sql, format_as_markdown=True)
            return results
        except Exception as e:
            # CRITICAL: Attempt to rollback session to prevent 'current transaction is aborted' errors
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

    def _professional_summary(self, user_input: str, explanation: str, results: Any) -> str:
        """Generate a professional executive-level narrative for the query results."""
        try:
            results_preview = str(results)[:2000] if results else "No results returned."
            prompt = (
                "You are a Senior Financial & Resource Planning Analyst presenting findings to executives.\n\n"
                "**Guidelines:**\n"
                "1. Write a professional, clear summary (3-6 sentences) interpreting the data results below.\n"
                "2. Highlight key figures, notable trends, or outliers.\n"
                "3. Use precise financial/resource planning terminology.\n"
                "4. If the data shows comparison metrics (budget vs actual, plan vs demand), call out the variance.\n"
                "5. Do NOT repeat raw numbers verbatim — synthesize an insight.\n"
                "6. End with a brief actionable observation or recommendation where appropriate.\n\n"
                f"**Original Question:** {user_input}\n"
                f"**Query Explanation:** {explanation}\n"
                f"**Data Results (preview):**\n{results_preview}\n\n"
                "**Professional Summary:**"
            )
            return self.tools.llm_call(prompt)
        except Exception as e:
            logger.warning(f"Professional summary generation failed: {e}")
            return explanation

    def run(self, user_input: str, retry_limit: int = 3) -> Dict[str, Any]:
        sql, explanation = self.get_sql(user_input)
        if not sql:
            return {"status": "error", "message": "Failed to generate SQL"}

        current_try = 0
        while current_try < retry_limit:
            try:
                results = self.execute_query(sql)

                # Generate professional narrative from the results
                professional_explanation = self._professional_summary(
                    user_input, explanation, results
                )

                return {
                    "status": "success",
                    "sql": sql,
                    "explanation": professional_explanation,
                    "results": results
                }
            except Exception as e:
                logger.warning(f"Attempt {current_try+1} failed: {e}")
                sql = self.fix_sql(sql, explanation, str(e))
                current_try += 1

        return {
            "status": "error",
            "message": "Exceeded retry limit",
            "last_sql": sql
        }