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

**Step A:** Copy the example env file and set your QGenie API key:

```bash
cp env.example .env
```

Open `.env` and set your API key:

```env
QGENIE_API_KEY=your-actual-api-key
```

**Step B:** Review `config/config.yaml` — this is the single source of truth for all settings including PostgreSQL credentials. The Postgres section looks like this:

```yaml
Postgres:
  host: "localhost"
  port: 5432
  database: "cnss_opex_db"
  admin_username: "postgres"      # used by bootstrap_db.py / drop_db.py
  admin_password: "postgres"      # used by bootstrap_db.py / drop_db.py
  username: "fira_user"           # used by the app at runtime
  password: "fira_password"       # used by the app at runtime
```

> **Note:** The admin credentials are only used during database bootstrap to create the database, enable extensions, and transfer table ownership. The application itself connects using the `username` / `password` credentials at runtime.

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

### Create the Application User (Manual — One Time)

Before running the bootstrap, create a dedicated application user in PostgreSQL. This separates admin operations from runtime access and follows the principle of least privilege.

**Option A — via psql (recommended):**

```bash
# Connect as the postgres superuser
psql -U postgres
```

```sql
-- Create the application role
CREATE ROLE fira_user WITH LOGIN PASSWORD 'your_fira_password';

-- Create the database
CREATE DATABASE cnss_opex_db OWNER postgres;

-- Connect to the new database
\c cnss_opex_db

-- Enable pgvector extension (requires superuser)
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant full privileges to the application user
GRANT CONNECT ON DATABASE cnss_opex_db TO fira_user;
GRANT USAGE, CREATE ON SCHEMA public TO fira_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO fira_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO fira_user;

-- Transfer ownership of FIRA tables (needed for CREATE INDEX, TRUNCATE)
ALTER TABLE IF EXISTS opex_data_hybrid OWNER TO fira_user;
ALTER TABLE IF EXISTS bpafg_demand OWNER TO fira_user;
ALTER TABLE IF EXISTS priority_template OWNER TO fira_user;
ALTER TABLE IF EXISTS chat_sessions OWNER TO fira_user;
ALTER TABLE IF EXISTS chat_messages OWNER TO fira_user;

-- Ensure future tables are also accessible
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL PRIVILEGES ON TABLES TO fira_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL PRIVILEGES ON SEQUENCES TO fira_user;

\q
```

**Option B — Automated via bootstrap (creates user automatically):**

If you skip the manual step above, the bootstrap script will create the `fira_user` role automatically using the admin credentials from `config/config.yaml`.

### Bootstrap the Database

The bootstrap script handles the complete database setup automatically:

1. Creates the `cnss_opex_db` database if it doesn't exist
2. Enables the pgvector extension
3. Creates the application user (`fira_user`) and grants privileges
4. Creates all three application tables (`opex_data_hybrid`, `bpafg_demand`, `priority_template`)
5. Applies all indexes (including IVFFlat vector similarity index)
6. Validates existing schemas and reports any column mismatches

```bash
python bootstrap_db.py
```

You can also pass a custom config path:

```bash
python bootstrap_db.py --config config/config.yaml
```

> **Note:** The bootstrap is fully idempotent — safe to run multiple times. Existing tables are validated rather than recreated.

> **Troubleshooting:** If you get `could not access file "$libdir/vector"`, re-run the pgvector installation steps for your OS and restart PostgreSQL before running the bootstrap again.

### Nuclear Reset — Drop Everything and Start Fresh

If you need to completely wipe all tables and recreate them with proper privileges (e.g., after a permission error or schema change):

**Step 1 — Drop all FIRA tables:**

```bash
python db/drop_db.py               # interactive — type DELETE to confirm
python db/drop_db.py --force       # skip confirmation (automation/CI)
```

This drops all 7 FIRA tables in dependency-safe order: `chat_messages`, `chat_sessions`, `opex_data_hybrid`, `bpafg_demand`, `priority_template`, `langchain_pg_embedding`, `langchain_pg_collection`.

**Step 2 — (Optional) Drop and recreate the application user:**

If you also need to reset the user/password:

```bash
psql -U postgres -d cnss_opex_db
```

```sql
-- Revoke and drop the old user
REASSIGN OWNED BY fira_user TO postgres;
DROP OWNED BY fira_user;
DROP ROLE IF EXISTS fira_user;

-- Recreate with a new password
CREATE ROLE fira_user WITH LOGIN PASSWORD 'new_password';
```

Then update `password` in the Postgres section of `config/config.yaml`.

**Step 3 — Re-bootstrap (recreates tables + grants privileges):**

```bash
python bootstrap_db.py
```

**Step 4 — Re-ingest data:**

```bash
python main.py                                                               # OpEx
python -m utils.parsers.cbn_data_parser --db postgres --data-dir ../files/resource  # Resource
```

**Step 5 — Verify:**

```bash
psql -U fira_user -d cnss_opex_db -c "\dt"
# Should list: opex_data_hybrid, bpafg_demand, priority_template
```

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
│   ├── config.py                   #   Unified config loader (YAML-first, .env for API keys)
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
python db/clear_db.py                 # Clears opex_data_hybrid (default)
python db/clear_db.py --table bpafg_demand         # Specific table
python db/clear_db.py --table priority_template     # Specific table
python db/clear_db.py --force         # Skip confirmation (automation)

# Drop ALL tables (interactive confirmation)
python db/drop_db.py                  # Drops all 7 FIRA tables
python db/drop_db.py --force          # Skip confirmation (automation)
```

After dropping tables, re-run `python bootstrap_db.py` and data ingestion to rebuild.

### Useful psql Commands

```bash
# Connect as the application user (recommended for queries)
psql -U fira_user -d cnss_opex_db

# Connect as admin (for DDL / troubleshooting)
psql -U postgres -d cnss_opex_db
```

```sql
-- Check tables and permissions
\dt                                     -- List all tables
\dp                                     -- Show table privileges
\du fira_user                           -- Show user roles

-- Describe tables
\d opex_data_hybrid                     -- OpEx hybrid table
\d bpafg_demand                         -- Demand table
\d priority_template                    -- Priority table

-- Row counts
SELECT COUNT(*) FROM opex_data_hybrid;
SELECT COUNT(*) FROM bpafg_demand;
SELECT COUNT(*) FROM priority_template;

-- Verify app user can query
SET ROLE fira_user;
SELECT COUNT(*) FROM opex_data_hybrid;
RESET ROLE;
```

---

## Configuration Reference

All settings are configured in `config/config.yaml`. Only `QGENIE_API_KEY` goes in `.env`.

| Setting | YAML Path | Default |
|---------|-----------|---------|
| OpEx Files Path | `Path.source_path` | `../files/opex` |
| Resource Files Path | `Path.resource_path` | `../files/resource` |
| JSONL Output Path | `Path.out_path` | `out` |
| Excel File Names | `Excel.file_names` | *(comma-separated list)* |
| DB Host | `Postgres.host` | `localhost` |
| DB Port | `Postgres.port` | `5432` |
| DB Name | `Postgres.database` | `cnss_opex_db` |
| DB Admin User | `Postgres.admin_username` | `postgres` |
| DB Admin Password | `Postgres.admin_password` | `postgres` |
| DB App User | `Postgres.username` | `fira_user` |
| DB App Password | `Postgres.password` | `fira_password` |
| LLM API Key | `.env` → `QGENIE_API_KEY` | — |
| LLM Model | `Qgenie.model_name` | `qgenie` |
| Chat Endpoint | `Qgenie.chat_endpoint` | — |
| Coding Model | `Qgenie.coding_model_name` | `anthropic::claude-4-sonnet` |
| Reasoning Model | `Qgenie.reasoning_model_name` | `azure::gpt-5.2` |
| Streamlit Port | `Streamlit.port` | `8507` |
| Feedback Email | `Feedback.email_id` | — |

---

## Quick Start Summary

```bash
# 1. Clone and setup
git clone <repository-url> && cd fira
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp env.example .env          # Edit: set QGENIE_API_KEY
# Review config/config.yaml  # Adjust DB credentials, host, port, models as needed

# 3. Create data directories
mkdir -p ../files/opex ../files/resource

# 4. Bootstrap database (creates DB, extension, app user, all tables, privileges)
python bootstrap_db.py

# 5. Verify app user can connect
psql -U fira_user -d cnss_opex_db -c "SELECT 1"

# 6. Ingest data (optional — can also use Data Mgmt UI)
python main.py                                                    # OpEx
python -m utils.parsers.cbn_data_parser --db postgres --data-dir ../files/resource  # Resource

# 7. Launch
python -m ui.launch           # Opens at http://localhost:8507
```

---

## License

See [LICENSE](LICENSE) for details.
