"""
FIRA — Financial Intelligence & Resource Analytics — Unified Database Setup

Creates and validates ALL database objects:
  1. Database  : cnss_opex_db (if not exists)
  2. Extension : pgvector
  3. Tables    : opex_data_hybrid, bpafg_demand, priority_template
  4. Indexes   : all required indexes for each table
  5. Schema    : validates columns match expected definitions

Usage:
    python -m db.setup_all_tables          # default config
    python -m db.setup_all_tables --config config/config.yaml

Called automatically by bootstrap_db.py.
"""

import logging
import os
import sys
import yaml
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Expected schema definitions (source of truth)
# ---------------------------------------------------------------------------

# -- opex_data_hybrid --
OPEX_TABLE = "opex_data_hybrid"
OPEX_EXPECTED_COLUMNS = {
    "id":              "integer",
    "uuid":            "uuid",
    "source_file":     "text",
    "source_sheet":    "text",
    "fiscal_year":     "integer",
    "project_number":  "bigint",
    "dept_lead":       "text",
    "hw_sw":           "text",
    "tm1_mm":          "numeric",
    "ods_mm":          "numeric",
    "vector":          "USER-DEFINED",   # pgvector type
    "additional_data": "jsonb",
    "created_at":      "timestamp with time zone",
    "updated_at":      "timestamp with time zone",
}

# -- bpafg_demand --
BPAFG_TABLE = "bpafg_demand"
BPAFG_EXPECTED_COLUMNS = {
    "id":                      "integer",
    "resource_name":           "text",
    "project_name":            "text",
    "task_name":               "text",
    "homegroup":               "text",
    "resource_security_group": "text",
    "primary_bl":              "text",
    "dept_country":            "text",
    "demand_type":             "text",
    "month":                   "text",
    "value":                   "numeric",
    "source_file":             "text",
    "created_at":              "timestamp without time zone",
}

# -- priority_template --
PRIORITY_TABLE = "priority_template"
PRIORITY_EXPECTED_COLUMNS = {
    "id":               "integer",
    "project":          "text",
    "priority":         "integer",
    "country":          "text",
    "target_capacity":  "numeric",
    "country_cost":     "numeric",
    "month":            "text",
    "monthly_capacity": "numeric",
    "source_file":      "text",
    "created_at":       "timestamp without time zone",
}


# ---------------------------------------------------------------------------
# SQL DDL statements
# ---------------------------------------------------------------------------

OPEX_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS opex_data_hybrid (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL,
    source_file TEXT,
    source_sheet TEXT,
    fiscal_year INTEGER,
    project_number BIGINT,
    dept_lead TEXT,
    hw_sw TEXT,
    tm1_mm NUMERIC(18, 6),
    ods_mm NUMERIC(18, 6),
    vector vector(1024),
    additional_data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""

OPEX_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_hybrid_uuid ON opex_data_hybrid(uuid);",
    "CREATE INDEX IF NOT EXISTS idx_hybrid_fiscal_year ON opex_data_hybrid(fiscal_year);",
    "CREATE INDEX IF NOT EXISTS idx_hybrid_project_number ON opex_data_hybrid(project_number);",
    "CREATE INDEX IF NOT EXISTS idx_hybrid_dept_lead ON opex_data_hybrid(dept_lead);",
    "CREATE INDEX IF NOT EXISTS idx_hybrid_hw_sw ON opex_data_hybrid(hw_sw);",
    "CREATE INDEX IF NOT EXISTS idx_hybrid_additional_data ON opex_data_hybrid USING GIN(additional_data);",
    "CREATE INDEX IF NOT EXISTS idx_hybrid_vector ON opex_data_hybrid USING ivfflat (vector vector_cosine_ops) WITH (lists = 100);",
]

BPAFG_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS bpafg_demand (
    id              SERIAL PRIMARY KEY,
    resource_name   TEXT,
    project_name    TEXT,
    task_name       TEXT,
    homegroup       TEXT,
    resource_security_group TEXT,
    primary_bl      TEXT,
    dept_country    TEXT,
    demand_type     TEXT,
    month           TEXT          NOT NULL,
    value           NUMERIC(12,4) DEFAULT 0,
    source_file     TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

BPAFG_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_bpafg_project   ON bpafg_demand(project_name);",
    "CREATE INDEX IF NOT EXISTS idx_bpafg_country   ON bpafg_demand(dept_country);",
    "CREATE INDEX IF NOT EXISTS idx_bpafg_homegroup ON bpafg_demand(homegroup);",
    "CREATE INDEX IF NOT EXISTS idx_bpafg_primary   ON bpafg_demand(primary_bl);",
    "CREATE INDEX IF NOT EXISTS idx_bpafg_demand    ON bpafg_demand(demand_type);",
    "CREATE INDEX IF NOT EXISTS idx_bpafg_month     ON bpafg_demand(month);",
]

PRIORITY_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS priority_template (
    id              SERIAL PRIMARY KEY,
    project         TEXT,
    priority        INTEGER,
    country         TEXT,
    target_capacity NUMERIC(12,4),
    country_cost    NUMERIC(12,4),
    month           TEXT,
    monthly_capacity NUMERIC(12,4),
    source_file     TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

PRIORITY_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_prio_project ON priority_template(project);",
    "CREATE INDEX IF NOT EXISTS idx_prio_country ON priority_template(country);",
    "CREATE INDEX IF NOT EXISTS idx_prio_month   ON priority_template(month);",
]


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_pg_config(config_path: str = "config/config.yaml") -> dict:
    """Load Postgres connection params from config YAML + .env overrides."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    pg = cfg.get("Postgres", {})

    # Allow .env overrides (same keys as Config dataclass)
    from dotenv import load_dotenv, find_dotenv
    for env_file in [".default.env", ".env"]:
        env_path = find_dotenv(env_file)
        if env_path:
            load_dotenv(env_path, override=True)

    host     = os.environ.get("POSTGRES_HOST",     pg.get("host", "localhost"))
    port     = int(os.environ.get("POSTGRES_PORT",  pg.get("port", 5432)))
    database = os.environ.get("POSTGRES_DB_NAME",   pg.get("database", "cnss_opex_db"))
    user     = os.environ.get("POSTGRES_ADMIN_USER", pg.get("user") or pg.get("username", "postgres"))
    password = os.environ.get("POSTGRES_ADMIN_PWD",  pg.get("password", "postgres"))

    return {
        "host": host,
        "port": port,
        "database": database,
        "user": user,
        "password": password,
    }


# ---------------------------------------------------------------------------
# Core setup logic
# ---------------------------------------------------------------------------

class DatabaseBootstrap:
    """
    Comprehensive database bootstrap that:
      1. Creates the target database if it doesn't exist
      2. Enables the pgvector extension
      3. Creates all application tables
      4. Creates all indexes
      5. Validates existing schemas (reports missing columns)
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path
        self.pg_config = load_pg_config(config_path)
        self.issues: List[str] = []

    # -- connection helpers --------------------------------------------------

    def _connect_admin(self):
        """Connect to the default 'postgres' database (for CREATE DATABASE)."""
        import psycopg2
        params = dict(self.pg_config)
        params["database"] = "postgres"
        conn = psycopg2.connect(**params)
        conn.autocommit = True
        return conn

    def _connect_app(self):
        """Connect to the application database."""
        import psycopg2
        conn = psycopg2.connect(**self.pg_config)
        conn.autocommit = False
        return conn

    # -- step 1: ensure database exists -------------------------------------

    def ensure_database(self) -> None:
        """Create the application database if it doesn't exist."""
        db_name = self.pg_config["database"]
        logger.info(f"Checking if database '{db_name}' exists...")

        conn = self._connect_admin()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
            )
            exists = cur.fetchone() is not None
            if exists:
                logger.info(f"  ✅ Database '{db_name}' already exists.")
            else:
                logger.info(f"  Creating database '{db_name}'...")
                cur.execute(f'CREATE DATABASE "{db_name}"')
                logger.info(f"  ✅ Database '{db_name}' created.")
            cur.close()
        finally:
            conn.close()

    # -- step 1b: ensure application user exists -----------------------------

    def ensure_app_user(self) -> None:
        """Create the application-level database user (fira_user) if it doesn't exist."""
        db_name = self.pg_config["database"]

        # Determine app user credentials from .env / config
        app_user = os.environ.get("POSTGRES_USER", "fira_user")
        app_pwd = os.environ.get("POSTGRES_PWD", "fira_password")

        logger.info(f"Checking application user '{app_user}'...")
        conn = self._connect_app()
        try:
            cur = conn.cursor()

            # Check if role already exists
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (app_user,))
            exists = cur.fetchone() is not None

            if not exists:
                logger.info(f"  Creating role '{app_user}'...")
                cur.execute(
                    f"CREATE ROLE \"{app_user}\" WITH LOGIN PASSWORD %s", (app_pwd,)
                )
                logger.info(f"  ✅ Role '{app_user}' created.")
            else:
                logger.info(f"  ✅ Role '{app_user}' already exists.")

            # Grant privileges: CONNECT, schema usage, and table-level access
            cur.execute(f'GRANT CONNECT ON DATABASE "{db_name}" TO "{app_user}"')
            cur.execute(f'GRANT USAGE, CREATE ON SCHEMA public TO "{app_user}"')
            cur.execute(f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "{app_user}"')
            cur.execute(f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "{app_user}"')

            # Transfer ownership of existing FIRA tables to the app user
            # (required for CREATE INDEX, TRUNCATE, ALTER TABLE, etc.)
            fira_tables = [
                "opex_data_hybrid", "bpafg_demand", "priority_template",
                "headcount_data",
                "chat_sessions", "chat_messages",
                "langchain_pg_collection", "langchain_pg_embedding",
            ]
            for table in fira_tables:
                try:
                    cur.execute(f'ALTER TABLE IF EXISTS {table} OWNER TO "{app_user}"')
                except Exception:
                    pass  # table may not exist yet — that's OK

            # Transfer ownership of sequences too
            cur.execute("""
                SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'
            """)
            for row in cur.fetchall():
                try:
                    cur.execute(f'ALTER SEQUENCE {row[0]} OWNER TO "{app_user}"')
                except Exception:
                    pass

            # Set default privileges so future tables are also accessible
            cur.execute(
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                f'GRANT ALL PRIVILEGES ON TABLES TO "{app_user}"'
            )
            cur.execute(
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                f'GRANT ALL PRIVILEGES ON SEQUENCES TO "{app_user}"'
            )

            conn.commit()
            logger.info(f"  ✅ Privileges granted to '{app_user}' on '{db_name}'.")
            cur.close()
        except Exception as e:
            conn.rollback()
            logger.error(f"  ❌ Failed to setup app user: {e}")
            self.issues.append(f"User setup failed: {e}")
        finally:
            conn.close()

    # -- step 2: enable pgvector --------------------------------------------

    def ensure_vector_extension(self) -> None:
        """Enable pgvector extension in the application database."""
        logger.info("Checking pgvector extension...")
        conn = self._connect_app()
        try:
            cur = conn.cursor()
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.commit()
            logger.info("  ✅ pgvector extension enabled.")
            cur.close()
        except Exception as e:
            conn.rollback()
            msg = str(e).lower()
            if "could not access file" in msg or "could not open" in msg:
                logger.error(
                    "  ❌ pgvector is not installed on this PostgreSQL server.\n"
                    "     Install it first — see README.md for instructions."
                )
            elif "permission denied" in msg:
                logger.error(
                    "  ❌ Permission denied. Run as a superuser or ask your DBA:\n"
                    "       CREATE EXTENSION IF NOT EXISTS vector;"
                )
            raise
        finally:
            conn.close()

    # -- step 3 & 4: create tables + indexes --------------------------------

    def _ensure_table(
        self,
        table_name: str,
        create_sql: str,
        indexes_sql: List[str],
        expected_columns: Dict[str, str],
    ) -> None:
        """Create a table if missing, validate its schema, and apply indexes."""
        conn = self._connect_app()
        try:
            cur = conn.cursor()

            # Check existence
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                )
                """,
                (table_name,),
            )
            exists = cur.fetchone()[0]

            if not exists:
                logger.info(f"  Table '{table_name}' not found — creating...")
                cur.execute(create_sql)
                conn.commit()
                logger.info(f"  ✅ Table '{table_name}' created.")
            else:
                logger.info(f"  ✅ Table '{table_name}' exists. Validating schema...")
                self._validate_schema(cur, table_name, expected_columns)

            # Apply indexes (idempotent)
            for idx_sql in indexes_sql:
                try:
                    cur.execute(idx_sql)
                except Exception as idx_err:
                    # Some indexes (e.g., ivfflat) may fail on empty tables — that's OK
                    logger.debug(f"  Index note: {idx_err}")
            conn.commit()
            logger.info(f"  ✅ Indexes verified for '{table_name}'.")

            cur.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _validate_schema(
        self, cursor, table_name: str, expected_columns: Dict[str, str]
    ) -> None:
        """Compare actual columns against expected; report mismatches."""
        cursor.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        actual = {row[0]: row[1] for row in cursor.fetchall()}

        # Check for missing columns
        for col, expected_type in expected_columns.items():
            if col not in actual:
                issue = f"  ⚠️  [{table_name}] Missing column: '{col}' (expected {expected_type})"
                logger.warning(issue)
                self.issues.append(issue)
            else:
                actual_type = actual[col]
                # Flexible type comparison (e.g., "numeric" matches "numeric")
                if not self._types_compatible(expected_type, actual_type):
                    issue = (
                        f"  ⚠️  [{table_name}] Column '{col}': "
                        f"expected '{expected_type}', found '{actual_type}'"
                    )
                    logger.warning(issue)
                    self.issues.append(issue)

        # Check for extra columns (informational only)
        extra = set(actual.keys()) - set(expected_columns.keys())
        if extra:
            logger.info(f"  ℹ️  [{table_name}] Extra columns (OK): {sorted(extra)}")

    @staticmethod
    def _types_compatible(expected: str, actual: str) -> bool:
        """Loose type comparison to handle Postgres type aliases."""
        e = expected.lower().strip()
        a = actual.lower().strip()

        # Direct match
        if e == a:
            return True

        # Common equivalences
        aliases = {
            "integer": {"integer", "int", "int4", "serial"},
            "bigint": {"bigint", "int8", "bigserial"},
            "text": {"text", "character varying", "varchar"},
            "numeric": {"numeric", "decimal", "real", "double precision"},
            "jsonb": {"jsonb"},
            "uuid": {"uuid"},
            "user-defined": {"user-defined"},  # pgvector
            "timestamp without time zone": {"timestamp without time zone", "timestamp"},
            "timestamp with time zone": {"timestamp with time zone", "timestamptz"},
        }
        for canonical, variants in aliases.items():
            if e in variants and a in variants:
                return True
            if e == canonical and a in variants:
                return True

        return False

    # -- orchestrator -------------------------------------------------------

    def run(self) -> bool:
        """
        Execute the full bootstrap sequence.
        Returns True if all steps passed, False if there were schema issues.
        """
        logger.info("=" * 60)
        logger.info("  FIRA — Database Bootstrap")
        logger.info("=" * 60)

        # Step 1: Ensure database exists
        self.ensure_database()

        # Step 2: Enable pgvector
        self.ensure_vector_extension()

        # Step 3: Create / validate tables
        logger.info("\nSetting up tables...")

        logger.info(f"\n[1/3] {OPEX_TABLE}")
        self._ensure_table(OPEX_TABLE, OPEX_CREATE_SQL, OPEX_INDEXES_SQL, OPEX_EXPECTED_COLUMNS)

        logger.info(f"\n[2/3] {BPAFG_TABLE}")
        self._ensure_table(BPAFG_TABLE, BPAFG_CREATE_SQL, BPAFG_INDEXES_SQL, BPAFG_EXPECTED_COLUMNS)

        logger.info(f"\n[3/3] {PRIORITY_TABLE}")
        self._ensure_table(PRIORITY_TABLE, PRIORITY_CREATE_SQL, PRIORITY_INDEXES_SQL, PRIORITY_EXPECTED_COLUMNS)

        # Step 4: Ensure application user and transfer ownership
        # IMPORTANT: this must run AFTER tables are created so that
        # ALTER TABLE ... OWNER TO actually finds the tables.
        self.ensure_app_user()

        # Summary
        logger.info("\n" + "=" * 60)
        if self.issues:
            logger.warning(f"  ⚠️  Bootstrap completed with {len(self.issues)} schema issue(s):")
            for issue in self.issues:
                logger.warning(f"    {issue}")
            logger.warning("  Review the issues above — you may need to ALTER TABLE or recreate.")
        else:
            logger.info("  🎉 All tables created and schemas validated successfully!")
        logger.info("=" * 60)

        return len(self.issues) == 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(description="FIRA — Database Bootstrap")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config.yaml (default: config/config.yaml)",
    )
    args = parser.parse_args()

    bootstrap = DatabaseBootstrap(config_path=args.config)
    success = bootstrap.run()

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
