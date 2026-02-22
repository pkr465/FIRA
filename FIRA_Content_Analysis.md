# FIRA — Content Analysis Report

**Financial Intelligence & Resource Analytics** | v2.1
*Analysis Date: February 21, 2026*

---

## What FIRA Is

FIRA is an enterprise-grade financial analytics platform built for Qualcomm's finance teams. It combines interactive resource planning, AI-powered data analysis, and comprehensive OpEx (Operational Expense) intelligence into a single Streamlit-based web dashboard. The platform is designed for finance directors, VPs, and program managers who need precision analytics for budget tracking, headcount demand planning, and capacity forecasting.

---

## Architecture Overview

FIRA follows a layered architecture with four main tiers:

**UI Layer** (Streamlit) → **Agent Layer** (Multi-agent AI pipeline) → **Service Layer** (Chat, Persistence) → **Data Layer** (PostgreSQL + pgvector)

The stack is Python 3.12+, backed by PostgreSQL 16 with pgvector for hybrid vector/relational search, and uses Qualcomm's internal QGenie LLM service (wrapping models like Claude 4 Sonnet and GPT-5.2) for all AI capabilities.

---

## Layer-by-Layer Content Analysis

### 1. Configuration Layer (`config/`)

The configuration system uses a two-tier approach: `config.yaml` for all application settings and `.env` for secrets. A `_Config` dataclass singleton loads YAML first, then overrides with environment variables. The config covers paths, database connections, LLM model selection (QGenie, Anthropic, Azure, Gemini), agent tuning parameters, and Streamlit settings.

Supporting config files include `schema.yaml` (defines the `opex_data_hybrid` table DDL with 1024-dim vector column), `labels.yaml` (maps business terms to database columns), `prompt.yaml` (few-shot prompts for a spreadsheet manipulation agent), and `API_document.yaml` (agent API docs). The `schema_config.py` and `labeling.py` modules parse these YAML files into runtime-usable formats — the labeling module is particularly important as it translates natural language terms like "spend" or "manager" into actual column names like `ods_mm` or `dept_lead`.

### 2. Agent Layer (`agents/`)

This is the intelligence core, built as a multi-agent pipeline:

- **OrchestrationAgent** — The top-level entry point. It receives user queries and delegates to the `UserIntentAgent`. Maintains a simple session state (input, response, metadata). Clean and minimal — just a thin wrapper.

- **UserIntentAgent** — The router/gatekeeper. Uses an LLM call to classify queries into three categories: `DATA_SQL_QUERY`, `SEMANTIC_SEARCH`, or `GENERAL_CHAT`. For SQL queries, it also generates a "refined query" that translates business terms into database column names. Routes to the appropriate sub-agent with a confidence threshold of 0.60.

- **SQLQueryAgent** — The workhorse for data questions. Contains rich schema definitions for all three tables (`opex_data_hybrid`, `bpafg_demand`, `priority_template`) with detailed column mappings. Generates SQL via LLM, executes against PostgreSQL, auto-retries up to 3 times with error-fixing prompts, and produces executive-level narrative summaries of query results. Handles the JSONB extraction patterns needed for `opex_data_hybrid`'s `additional_data` column.

- **SemanticSearchAgent** — Handles RAG (Retrieval Augmented Generation) for policy/document questions. Expands queries using LLM-generated synonyms, performs vector similarity search, deduplicates results, and synthesizes answers grounded in retrieved document fragments with source citations.

- **ChatbotAgent** — The conversational fallback for greetings, help requests, and off-topic queries. Has a built-in capabilities menu and maintains a professional FIRA persona. Redirects non-financial questions back to the platform's domain.

- **DataVisualizationAgent** — A lightweight module that converts retrieved data into Plotly charts via LLM-generated code. Currently appears to be a prototype/stub.

- **AgentUtils** — Shared toolkit providing LLM calls (via QGenie), database connections, embedding clients, and vector retriever access with retry logic.

### 3. Chat Service Layer (`chat/`)

- **ChatService** — High-level facade connecting the UI to the orchestration pipeline. Manages session IDs, persists user messages and bot responses, and provides a CLI mode for testing.

- **ChatPersistenceService** — SQLAlchemy-based persistence with two tables: `chat_sessions` (session tracking with timestamps and summaries) and `chat_messages` (individual messages with roles and extras). Supports session creation, message saving, history retrieval, and session deletion with cascade behavior.

- **Prompts** — Defines the `SYSTEM_PROMPT` constant — a comprehensive persona definition for FIRA's AI. Specifies executive-quality response formatting, data handling rules, financial precision requirements, and analytical boundaries.

### 4. Database Layer (`db/`)

- **setup_all_tables.py** — Unified bootstrap that creates the database, enables pgvector, creates all three tables with indexes, and validates existing schemas with mismatch reporting.

- **cbn_tables.py** — DDL and query helpers for the two resource planning tables (`bpafg_demand`, `priority_template`). Supports both PostgreSQL and SQLite backends.

- **data_pipeline.py** — Orchestrates the full OpEx ingestion workflow: schema init → Excel-to-JSONL conversion → vector embedding generation → database ingestion.

- **embedding_client.py** — QGenie SDK wrapper for generating 1024-dimensional vector embeddings from text.

- **vector_store.py** — Handles document persistence to `opex_data_hybrid` with UUID-based deduplication and batch processing.

- **vector_retriever.py** — Hybrid search using cosine similarity with configurable metadata filters. Returns relevance-ranked results.

### 5. Utility Layer (`utils/`)

- **database.py / db_provider.py** — Database singleton with connection pooling, health checks, session management, and automatic connection refresh. The provider handles bulk inserts, UUID-based retrieval, and stale connection recovery.

- **cbn_data_parser.py** — Parses BPAFG demand and priority template files from CSV/XLSX, normalizing various month formats and melting wide-format data into long-form records for database insertion.

- **excel_to_json.py** — Converts OpEx Excel workbooks to JSONL with deterministic UUIDs based on content hashing. Respects existing output files to avoid reprocessing.

### 6. UI Layer (`ui/`)

Built entirely in Streamlit with 13 pages:

- **streamlit_app.py** — Main router with sidebar navigation, FIRA branding, and query-parameter-based page routing.

- **streamlit_tools.py** — Global CSS theme ("Greenback Finance" — a dollar-bill green palette with IBM Plex typography), plus utility functions for response extraction, chat context management, feedback widgets, and file uploads.

- **Welcome page** — Landing page with hero branding, quick-start guide, and organized navigation cards for all features.

- **Resource Planner** — The most complex page. Interactive mountain chart (stacked area) with priority-based project stacking, demand vs. capacity analysis, per-country cost multipliers, project reordering with shift controls, hide/show toggles, editable allocation tables, snapshot save/load, and gap detection.

- **Data Management** — Unified upload/ingest interface with three tabs for OpEx (Excel + vector embeddings), Resource Planner (CSV/XLSX to PostgreSQL), and Headcount data. Includes table health monitoring.

- **AI ChatBot** — Natural language financial analysis interface with rich response formatting, auto-generated Plotly charts, markdown tables, KPI boxes, session management, and chat history summarization.

- **Summary** — Executive dashboard with FY Budget vs. Actual variance, project spend breakdowns, and LLM-generated commentary.

- **Financial Trends, Resource Allocation, Dept Rollup, Geo & Org** — Analytics pages for time-series trends, utilization views, department cost aggregation, and geographic/organizational comparisons.

- **Plotting Sandbox** — Custom visualization builder for ad-hoc analysis.

- **Chat History** — Browse and review past AI chat sessions.

- **FAQ / About** — Informational pages.

- **Feedback** — Modal that captures user feedback and emails it as formatted HTML to a configured recipient.

---

## Database Schema

| Table | Purpose | Key Columns | Vector Support |
|-------|---------|-------------|---------------|
| `opex_data_hybrid` | OpEx financials | UUID, fiscal_year, project_number, dept_lead, hw_sw, tm1_mm, ods_mm, additional_data (JSONB), vector (1024-dim) | Yes — IVFFlat cosine |
| `bpafg_demand` | Resource demand | resource_name, project_name, homegroup, dept_country, demand_type, month, value | No |
| `priority_template` | Project priority | project, priority, country, target_capacity, country_cost, month, monthly_capacity | No |
| `chat_sessions` | Chat tracking | session_id, created_at, updated_at, summary | No |
| `chat_messages` | Chat messages | session_id, role, content, timestamp | No |

---

## Technology Stack

- **Frontend**: Streamlit with custom CSS theming
- **Backend**: Python 3.12+
- **Database**: PostgreSQL 16 + pgvector
- **AI/LLM**: QGenie SDK (Qualcomm internal) wrapping Claude 4 Sonnet, GPT-5.2, Gemini 2.5 Pro
- **Embeddings**: QGenie embeddings (1024-dim), stored in pgvector
- **Data Processing**: Pandas, OpenPyXL, SQLAlchemy
- **Visualization**: Plotly, Matplotlib
- **Key Libraries**: LangChain (postgres), LangGraph, NetworkX, python-dotenv

---

## Key Observations

1. **Hybrid search architecture** — The `opex_data_hybrid` table cleverly combines structured SQL querying with vector similarity search through a JSONB + pgvector design, enabling both precise financial queries and semantic document retrieval from a single table.

2. **Multi-agent pipeline** — The intent → route → execute → summarize pattern is well-structured. The SQL agent's auto-retry with error-fixing prompts adds resilience to LLM-generated queries.

3. **Resource Planner sophistication** — The CBN Resource Planner page is the most feature-rich component, with interactive mountain charts, priority-based stacking, cost controls, and snapshot persistence — essentially a planning tool within the analytics platform.

4. **Configuration-driven** — Nearly everything is configurable via YAML, from database connections to LLM model selection to agent parameters, making the platform adaptable across environments.

5. **Qualcomm-internal dependencies** — The QGenie SDK and embedding service are internal to Qualcomm, meaning this platform is tightly coupled to Qualcomm's AI infrastructure.
