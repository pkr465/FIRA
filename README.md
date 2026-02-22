# FIRA — Financial Intelligence & Resource Analytics

**Resource Planner & OpEx Analytics** | v2.1

An enterprise-grade financial analytics platform combining interactive resource planning, AI-powered data analysis, and comprehensive OpEx intelligence — built for finance teams that demand precision.

---

## Features

- **FIRA Resource Planner** — Interactive mountain chart (stacked area) with priority-based project stacking, demand vs. capacity analysis, per-country cost controls, real-time gap detection, project hide/show toggle, and snapshot save/load
- **AI ChatBot** — Natural language queries across both OpEx financials and resource planning data, powered by a multi-agent pipeline (Intent → SQL/RAG/Chat) with auto-generated Plotly charts and professional executive-level analysis
- **Data Management** — Unified UI page for uploading and ingesting both OpEx Excel files (with vector embeddings) and Resource Planner CSVs, plus re-ingest controls and table health monitoring
- **Financial Analytics** — Executive summary dashboard, trend tracking, department rollups, resource allocation views, geo/org analytics, and a custom plotting sandbox
- **Data Ingestion** — Excel-to-JSONL conversion with QGenie vector embeddings for OpEx data, CSV/XLSX parsers for BPAFG demand and Priority Template files with automatic month normalization
- **Database Bootstrap** — Automated setup script that creates the database, enables pgvector, creates all tables, validates schemas, and reports mismatches
- **FIRA UI Theme** — Professional light-mode dollar-bill green color scheme with IBM Plex typography, designed for financial dashboard readability

---

## Prerequisites

- **Python 3.12+**
- **PostgreSQL 16** with pgvector extension
- **pip** package manager

---

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd fira
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows
python --version             # Verify Python 3.12+
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Install QGenie SDK (Internal)

```bash
pip install qgenie-sdk[all] qgenie-sdk-tools \
  -i https://devpi.qualcomm.com/qcom/dev/+simple \
  --trusted-host devpi.qualcomm.com
```

### 5. Configure Environment

The project uses two configuration layers:

- **`config/config.yaml`** — All application settings (paths, models, endpoints, DB host/port, Streamlit port, agent tuning, etc.)
- **`.env`** — Only secrets and credentials (API keys, database passwords)

**Step A:** Copy the example env file and fill in your secrets:

```bash
cp env.example .env
```

Open `.env` and set your credentials:

```env
QGENIE_API_KEY=your-actual-api-key
POSTGRES_ADMIN_USER=postgres
POSTGRES_ADMIN_PWD=postgres
POSTGRES_USER=your_db_user
POSTGRES_PWD=your_db_password
```

**Step B:** Review `config/config.yaml` and adjust settings for your environment — database host/port, LLM model names, chat endpoint, file paths, Streamlit port, agent parameters, etc. Secrets referenced via `NOTE` comments in the YAML are loaded from `.env` at runtime.

> **Note:** Never commit `.env` to version control. The `env.example` is the safe, credential-free template to share with your team.

### 6. Create Data Directories

Data files live outside the project folder in `../files/`:

```bash
mkdir -p ../files/opex        # OpEx Excel files
mkdir -p ../files/resource     # Resource Planner CSV/XLSX files
```

---

## Database Setup

### Remove Older PostgreSQL Versions (if needed)

If you have PostgreSQL 15 or older installed and want a clean upgrade to 16:

**Rocky Linux / RHEL:**

```bash
# Stop old service
sudo systemctl stop postgresql-15
sudo systemctl disable postgresql-15

# Remove old packages
sudo dnf remove -y postgresql15-server postgresql15-contrib postgresql15-libs pgvector_15

# Clean up data directory (CAUTION: back up data first if needed)
sudo rm -rf /var/lib/pgsql/15/
```

**macOS (Homebrew):**

```bash
brew services stop postgresql@15
brew uninstall postgresql@15
rm -rf /opt/homebrew/var/postgresql@15   # or /usr/local/var/postgresql@15 on Intel
```

**Windows:**

Uninstall via Control Panel → Programs and Features → PostgreSQL 15. Delete `C:\Program Files\PostgreSQL\15\` and your data directory after backup.

---

### Install PostgreSQL 16

#### Rocky Linux / RHEL 8+

```bash
# Add PostgreSQL 16 repository
sudo dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-8-x86_64/pgdg-redhat-repo-latest.noarch.rpm
sudo dnf -qy module disable postgresql

# Install PostgreSQL 16
sudo dnf install -y postgresql16-server postgresql16-contrib

# Initialize and start
sudo /usr/pgsql-16/bin/postgresql-16-setup initdb
sudo systemctl enable --now postgresql-16
sudo systemctl status postgresql-16
```

#### macOS (Homebrew)

```bash
# Install PostgreSQL 16
brew install postgresql@16

# Start the service
brew services start postgresql@16

# Add to PATH
echo 'export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Verify
psql --version    # Should show psql (PostgreSQL) 16.x
```

#### Windows

Download PostgreSQL 16 from https://www.postgresql.org/download/windows/ and follow the installer. After installation:

```powershell
& "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" -D "C:\Users\<username>\PostgresData" -l "C:\Users\<username>\pg_log.txt" start
```

---

### Install pgvector Extension

The platform uses `pgvector` for vector similarity search on OpEx data. **This must be installed before running the database bootstrap.** Without it, queries on `opex_data_hybrid` will fail with `could not access file "$libdir/vector"`.

#### Rocky Linux / RHEL 8+

```bash
# Install from PGDG repository
sudo dnf install -y pgvector_16
```

If the package is not found, install from source:

```bash
sudo dnf install -y postgresql16-devel gcc make git
cd /tmp
git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git
cd pgvector
make PG_CONFIG=/usr/pgsql-16/bin/pg_config
sudo make install PG_CONFIG=/usr/pgsql-16/bin/pg_config
```

#### macOS (Homebrew)

```bash
brew install pgvector
```

If the extension is not found after installation, build from source:

```bash
cd /tmp
git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git
cd pgvector
make PG_CONFIG=$(brew --prefix postgresql@16)/bin/pg_config
make install PG_CONFIG=$(brew --prefix postgresql@16)/bin/pg_config
```

#### Windows

Download a prebuilt pgvector release from https://github.com/pgvector/pgvector/releases matching PostgreSQL 16. Extract and copy:

- `vector.dll` → `C:\Program Files\PostgreSQL\16\lib\`
- `vector.control` and `vector--*.sql` → `C:\Program Files\PostgreSQL\16\share\extension\`

See https://github.com/pgvector/pgvector#windows for build-from-source instructions.

#### Verify pgvector

Restart PostgreSQL and verify:

```bash
sudo systemctl restart postgresql-16    # Rocky Linux
# brew services restart postgresql@16   # macOS
```

```bash
psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS vector;" -d template1
# Should succeed without errors
```

---

### Bootstrap the Database

The bootstrap script handles the complete database setup automatically:

1. Creates the `cnss_opex_db` database if it doesn't exist
2. Enables the pgvector extension
3. Creates all three application tables (`opex_data_hybrid`, `bpafg_demand`, `priority_template`)
4. Applies all indexes (including IVFFlat vector similarity index)
5. Validates existing schemas and reports any column mismatches

```bash
python bootstrap_db.py
```

You can also pass a custom config path:

```bash
python bootstrap_db.py --config config/config.yaml
```

> **Note:** The bootstrap is fully idempotent — safe to run multiple times. Existing tables are validated rather than recreated.

> **Troubleshooting:** If you get `could not access file "$libdir/vector"`, re-run the pgvector installation steps for your OS and restart PostgreSQL before running the bootstrap again.

---

## Data Ingestion

### File Organization

All data files are stored outside the project in `../files/`:

```
../files/
├── opex/                  # OpEx Excel files
│   ├── FY25 Q4 WIN Opex_data.xlsx
│   └── FY25 Q3 WIN Opex_data.xlsx
└── resource/              # Resource Planner files
    ├── BPAFG - Feb_05_2026.csv
    └── priority_template_rank0.csv
```

### OpEx Data (Excel → Vector Embeddings)

OpEx Excel files are converted to JSONL, embedded via QGenie, and stored in the `opex_data_hybrid` table with pgvector similarity search support. This enables the AI ChatBot to perform both SQL queries and semantic (RAG) retrieval over OpEx data.

**Option A — Command Line:**

Place files in `../files/opex/` and run:

```bash
python main.py
```

This executes the full pipeline: database bootstrap → Excel-to-JSONL conversion → vector embedding ingestion.

**Option B — Data Management UI:**

Navigate to the **Data Mgmt** page in the Streamlit app, upload OpEx Excel files, and click **Ingest Uploaded Files**. The same pipeline runs from the browser.

### FIRA Resource Planner Data (CSV → Relational Tables)

Resource Planner files are parsed and stored in standard relational tables (`bpafg_demand`, `priority_template`) for SQL analytics and the Resource Planner visualization. These tables do not use vector embeddings but are fully queryable through the AI ChatBot via SQL.

**Option A — Command Line:**

Place CSV or XLSX files in `../files/resource/` and run:

```bash
python -m utils.parsers.cbn_data_parser --db postgres --data-dir ../files/resource
```

File naming conventions:

- **BPAFG Demand files** — filenames containing "bpafg" (e.g., `BPAFG - Feb_05_2026.csv`)
- **Priority Template files** — filenames containing "priority" (e.g., `priority_template_rank0.csv`)

**Option B — Data Management UI:**

Navigate to the **Data Mgmt** page, upload demand and/or priority files, and click **Ingest Uploaded Files**. Files are automatically saved to `../files/resource/` and ingested into PostgreSQL.

**Option C — Resource Planner Page:**

The Resource Planner page also has built-in upload and ingest functionality for quick data loading.

---

## Running the Application

```bash
python -m ui.launch
```

The Streamlit port is configured in `config/config.yaml` under `Streamlit.port` (default: **8507**). The dashboard launches at **http://localhost:8507**. Access from another device on the same network using your machine's IP address.

### Pages

| Page | URL Slug | Description |
|------|----------|-------------|
| **Resource Planner** | `cbn_planner` | Mountain chart, capacity/cost panels, allocation table, project reordering, hide/show projects, snapshot save/load |
| **Data Mgmt** | `data_management` | Upload and ingest OpEx Excel files (with vector embeddings) and Resource Planner CSVs, table health monitoring with row counts |
| **Summary** | `summary` | Executive dashboard with FY summary, project spend breakdown, and LOE analysis |
| **Financial Trends** | `financial_trends` | Time-series trend analysis across fiscal periods |
| **Resource Alloc** | `resource_allocation` | Resource utilization and allocation views |
| **Dept Rollup** | `department_rollup` | Department-level cost aggregation and VP rollup analysis |
| **Geo & Org** | `geo_org` | Country-level and organizational spending comparisons |
| **Sandbox** | `sandbox` | Custom visualization builder |
| **ChatBot** | `chatbot` | AI-powered natural language financial and resource planning analysis with auto-charting |
| **FAQ** | `faq` | Searchable frequently asked questions |
| **About** | `about` | Platform overview and technology stack |
| **History** | `history` | Browse and review past AI chat sessions |

---

## AI ChatBot

The ChatBot uses a multi-agent orchestration pipeline that routes user questions to the appropriate handler:

- **Intent Agent** — Classifies queries as SQL data requests, semantic search, or general chat
- **SQL Agent** — Generates and executes PostgreSQL queries across all three tables (`opex_data_hybrid`, `bpafg_demand`, `priority_template`), then produces a professional executive-level narrative summarizing the results
- **Semantic Agent** — Performs RAG (Retrieval Augmented Generation) over vector-embedded OpEx documents for policy and explanatory questions
- **Chat Agent** — Handles greetings, help requests, and general conversation with professional tone

### Example Queries — OpEx Financial Analytics

- "What is the total spend across all cost centers in the latest quarter?"
- "Show me a detailed budget breakdown for the top 5 projects by spend."
- "Compare HW vs SW spending trends across the last 4 quarters."
- "Show budget vs actual variance for the current fiscal year."
- "List all unique department leads with their total managed budget."

### Example Queries — Resource Planner & Demand

- "What is the total headcount demand by project for the current month?"
- "Show me the FTE allocation for each homegroup across all projects."
- "What is the resource demand split by country?"
- "List all projects ranked by priority with their target capacity."
- "What is the cost per resource by country for the top 5 projects?"
- "Show me the monthly demand trend for the last 6 months by project."

---

## Project Structure

```
fira/
├── agents/                         # AI agent modules
│   ├── orchestration_agent.py      #   Main orchestrator (routes intent)
│   ├── user_intent_agent.py        #   Intent classification (3 tables aware)
│   ├── data_sql_query_agent.py     #   SQL gen across all tables + professional summary
│   ├── semantic_search_agent.py    #   RAG-based vector retrieval
│   ├── chatbot_agent.py            #   Conversational agent
│   ├── data_ingestion_agent.py     #   JSONL → vector embedding ingestion
│   ├── data_connector_agent.py     #   Data connection utilities
│   ├── data_visualization_agent.py #   Chart generation
│   └── report_agent.py             #   Report generation
├── chat/                           # Chat service layer
│   ├── chat_service.py             #   ChatService (orchestrator wrapper)
│   ├── chat_persistence.py         #   SQLAlchemy session/message persistence
│   └── prompts.py                  #   LLM system prompt configuration
├── config/                         # Configuration files
│   ├── config.py                   #   Unified config loader (YAML + .env)
│   ├── config.yaml                 #   Main configuration
│   ├── schema.yaml                 #   Vector DB schema definition (opex_data_hybrid)
│   ├── schema_config.py            #   Schema YAML loader and SQL formatter
│   ├── labeling.py                 #   Query-to-schema column mapper
│   ├── labels.yaml                 #   Column label definitions
│   ├── prompt.yaml                 #   Agent prompt templates
│   └── API_document.yaml           #   API documentation for agents
├── db/                             # Database layer
│   ├── setup_all_tables.py         #   Unified bootstrap (DB + extension + all tables)
│   ├── setup_db.py                 #   Legacy OpEx schema setup (DatabaseSetupManager)
│   ├── cbn_tables.py               #   FIRA table DDL (bpafg_demand, priority_template)
│   ├── data_pipeline.py            #   Excel → JSONL → vector ingestion pipeline
│   ├── embedding_client.py         #   QGenie embedding client wrapper
│   ├── vector_store.py             #   PGVector store (document upsert with embeddings)
│   ├── vector_retriever.py         #   Vector similarity search for RAG
│   ├── list_db.py                  #   List table rows utility
│   ├── clear_db.py                 #   Clear table data utility
│   ├── drop_db.py                  #   Drop tables utility
│   └── search_test.py              #   Vector search test harness
├── ui/                             # Streamlit frontend
│   ├── streamlit_app.py            #   Main app entry point and router
│   ├── streamlit_tools.py          #   Global CSS (FIRA theme) and utilities
│   ├── launch.py                   #   CLI launcher (reads port from config)
│   ├── .streamlit/config.toml      #   Streamlit theme configuration
│   └── modules/                    #   Page modules
│       ├── base.py                 #     PageBase class (CSS injection, routing)
│       ├── cbn_resource_planner.py #     Resource Planner page
│       ├── data_management.py      #     Data Management page (upload/ingest)
│       ├── chatbot.py              #     AI ChatBot page
│       ├── summary.py              #     Executive Summary dashboard
│       ├── metrics_financial_trends.py  # Financial Trends page
│       ├── metrics_resource_allocation.py # Resource Allocation page
│       ├── metrics_dept_rollup.py  #     Department Rollup page
│       ├── metrics_geo_org.py      #     Geo & Org Analytics page
│       ├── plotting_sandbox.py     #     Custom Plotting Sandbox
│       ├── chat_history.py         #     Chat History browser
│       ├── faq.py                  #     FAQ page
│       ├── about.py                #     About page
│       └── feedback_ui.py          #     Feedback widget component
├── utils/                          # Utility modules
│   ├── parsers/
│   │   ├── cbn_data_parser.py      #   BPAFG + Priority Template parser
│   │   └── excel_to_json.py        #   OpEx Excel → JSONL converter
│   └── models/
│       ├── database.py             #   OpexDB engine, health check, session mgmt
│       ├── db_provider.py          #   Database provider abstraction
│       ├── opex_provider.py        #   OpEx data provider
│       └── win_opex.py             #   WIN OpEx model
├── env.example                     # Environment template (cp to .env)
├── bootstrap_db.py                 # Database bootstrap entry point
├── main.py                         # OpEx data ingestion CLI entry point
├── requirements.txt                # Python dependencies
└── README.md

../files/                           # Data files (outside project)
├── opex/                           #   OpEx Excel files
└── resource/                       #   Resource Planner CSV/XLSX files
```

---

## Database Architecture

The platform uses three PostgreSQL tables:

| Table | Purpose | Vector Support | Queried By |
|-------|---------|---------------|------------|
| `opex_data_hybrid` | OpEx financial data (spend, budget, departments, projects) | Yes — pgvector 1024-dim with IVFFlat index | ChatBot (SQL + RAG), Summary, Financial Trends, Dept Rollup, Geo & Org, Resource Alloc, Sandbox |
| `bpafg_demand` | Resource demand planning (headcount, FTE by project/country/month) | No — relational only | ChatBot (SQL), Resource Planner |
| `priority_template` | Project priority rankings and country capacity/cost | No — relational only | ChatBot (SQL), Resource Planner |

All tables are created and validated by `bootstrap_db.py` → `db/setup_all_tables.py`.

---

## Database Utilities

```bash
# List rows in the database
python db/list_db.py                  # Default: first 20 rows
python db/list_db.py --limit 5        # Specific count
python db/list_db.py --all            # All rows

# Clear data (interactive confirmation)
python db/clear_db.py
python db/clear_db.py --force         # Skip confirmation (automation)

# Drop tables (interactive confirmation)
python db/drop_db.py
python db/drop_db.py --force          # Skip confirmation (automation)
```

After dropping tables, re-run `python bootstrap_db.py` and data ingestion to rebuild.

### Useful psql Commands

```bash
psql -U postgres -d cnss_opex_db
```

```sql
\dt                                     -- List all tables
\d opex_data_hybrid                     -- Describe OpEx hybrid table
\d bpafg_demand                         -- Describe demand table
\d priority_template                    -- Describe priority table
SELECT COUNT(*) FROM opex_data_hybrid;
SELECT COUNT(*) FROM bpafg_demand;
SELECT COUNT(*) FROM priority_template;
SELECT DISTINCT project_name FROM bpafg_demand;
```

---

## Configuration Reference

All settings can be configured via `config/config.yaml` or environment variables (`.env`). Environment variables take precedence.

| Setting | YAML Path | Env Variable | Default |
|---------|-----------|-------------|---------|
| OpEx Files Path | `Path.source_path` | `SOURCE_PATH` | `../files/opex` |
| Resource Files Path | `Path.resource_path` | `RESOURCE_PATH` | `../files/resource` |
| JSONL Output Path | `Path.out_path` | `OUT_PATH` | `out` |
| Excel File Names | `Excel.file_names` | `EXCEL_FILE_NAMES` | *(comma-separated list)* |
| DB Connection | `Postgres.connection` | `POSTGRES_CONNECTION` | `postgresql+psycopg2://postgres:postgres@localhost/cnss_opex_db` |
| DB Host | `Postgres.host` | `POSTGRES_HOST` | `localhost` |
| DB Port | `Postgres.port` | `POSTGRES_PORT` | `5432` |
| DB Name | `Postgres.database` | `POSTGRES_DB_NAME` | `cnss_opex_db` |
| LLM API Key | *(secrets only — .env)* | `QGENIE_API_KEY` | — |
| LLM Model | `Qgenie.model_name` | — | `qgenie` |
| Chat Endpoint | `Qgenie.chat_endpoint` | `QGENIE_CHAT_ENDPOINT` | — |
| Coding Model | `Qgenie.coding_model_name` | — | `anthropic::claude-4-sonnet` |
| Reasoning Model | `Qgenie.reasoning_model_name` | — | `azure::gpt-5.2` |
| Streamlit Port | `Streamlit.port` | `STREAMLIT_PORT` | `8507` |
| Feedback Email | `Feedback.email_id` | `FEEDBACK_EMAIL_ID` | — |
| Log Level | — | `LOG_LEVEL` | `INFO` |

---

## Quick Start Summary

```bash
# 1. Clone and setup
git clone <repository-url> && cd fira
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp env.example .env          # Edit with your secrets
# Review config/config.yaml  # Adjust settings

# 3. Create data directories
mkdir -p ../files/opex ../files/resource

# 4. Bootstrap database (creates DB, extension, all tables)
python bootstrap_db.py

# 5. Ingest data (optional — can also use Data Mgmt UI)
python main.py                                                    # OpEx
python -m utils.parsers.cbn_data_parser --db postgres --data-dir ../files/resource  # Resource

# 6. Launch
python -m ui.launch           # Opens at http://localhost:8507
```

---

## License

See [LICENSE](LICENSE) for details.
