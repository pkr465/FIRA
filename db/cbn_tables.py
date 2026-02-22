"""
FIRA Resource Planner — Database Table Definitions & Helpers

Creates and manages two tables:
  1. bpafg_demand       – Tempus forecast demand data (from BPAFG CSVs)
  2. priority_template   – Project priority, country capacity & cost config

Works with PostgreSQL (production) or SQLite (testing).
"""

import logging
import os
import yaml
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL DDL
# ---------------------------------------------------------------------------

BPAFG_DEMAND_CREATE_SQL = """
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

BPAFG_DEMAND_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_bpafg_project   ON bpafg_demand(project_name);",
    "CREATE INDEX IF NOT EXISTS idx_bpafg_country   ON bpafg_demand(dept_country);",
    "CREATE INDEX IF NOT EXISTS idx_bpafg_homegroup ON bpafg_demand(homegroup);",
    "CREATE INDEX IF NOT EXISTS idx_bpafg_primary   ON bpafg_demand(primary_bl);",
    "CREATE INDEX IF NOT EXISTS idx_bpafg_demand    ON bpafg_demand(demand_type);",
    "CREATE INDEX IF NOT EXISTS idx_bpafg_month     ON bpafg_demand(month);",
]

PRIORITY_TEMPLATE_CREATE_SQL = """
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

PRIORITY_TEMPLATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_prio_project ON priority_template(project);",
    "CREATE INDEX IF NOT EXISTS idx_prio_country ON priority_template(country);",
    "CREATE INDEX IF NOT EXISTS idx_prio_month   ON priority_template(month);",
]

# SQLite-compatible versions (SERIAL → INTEGER PRIMARY KEY AUTOINCREMENT)
BPAFG_DEMAND_CREATE_SQL_SQLITE = BPAFG_DEMAND_CREATE_SQL.replace(
    "SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"
).replace("NUMERIC(12,4)", "REAL")

PRIORITY_TEMPLATE_CREATE_SQL_SQLITE = PRIORITY_TEMPLATE_CREATE_SQL.replace(
    "SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"
).replace("NUMERIC(12,4)", "REAL")


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def load_pg_config(config_path: str = "config/config.yaml") -> dict:
    """Load Postgres connection params from the project config YAML + .env overrides."""
    # Load .env so that POSTGRES_* env vars are available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    pg = cfg.get("Postgres", {})

    # Env vars take precedence over YAML values
    return {
        "host": os.environ.get("POSTGRES_HOST") or pg.get("host", "localhost"),
        "port": int(os.environ.get("POSTGRES_PORT", 0) or pg.get("port", 5432)),
        "database": os.environ.get("POSTGRES_DB_NAME") or pg.get("database") or pg.get("dbname", "cnss_opex_db"),
        "user": os.environ.get("POSTGRES_USER") or pg.get("username") or pg.get("user", "postgres"),
        "password": os.environ.get("POSTGRES_PWD") or os.environ.get("POSTGRES_ADMIN_PWD") or pg.get("password", "postgres"),
    }


def get_pg_connection(config_path: str = "config/config.yaml"):
    """Return a psycopg2 connection using project config."""
    import psycopg2
    params = load_pg_config(config_path)
    return psycopg2.connect(**params)


def get_pg_connection_string(config_path: str = "config/config.yaml") -> str:
    """Return SQLAlchemy-style connection string."""
    p = load_pg_config(config_path)
    return f"postgresql+psycopg2://{p['user']}:{p['password']}@{p['host']}:{p['port']}/{p['database']}"


@contextmanager
def get_sqlite_connection(db_path: str = "../files/resource/cbn_resource_planner.db"):
    """Context manager for a SQLite connection (for testing / lightweight use)."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------

def setup_tables_postgres(config_path: str = "config/config.yaml"):
    """Create tables + indexes in Postgres."""
    conn = get_pg_connection(config_path)
    try:
        with conn.cursor() as cur:
            cur.execute(BPAFG_DEMAND_CREATE_SQL)
            for idx in BPAFG_DEMAND_INDEXES_SQL:
                cur.execute(idx)
            cur.execute(PRIORITY_TEMPLATE_CREATE_SQL)
            for idx in PRIORITY_TEMPLATE_INDEXES_SQL:
                cur.execute(idx)
        conn.commit()
        logger.info("FIRA tables created in PostgreSQL.")
    finally:
        conn.close()


def setup_tables_sqlite(db_path: str = "../files/resource/cbn_resource_planner.db"):
    """Create tables + indexes in SQLite."""
    import sqlite3
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # Execute each statement individually (executescript auto-commits and can conflict)
        for stmt in BPAFG_DEMAND_CREATE_SQL_SQLITE.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)
        for idx in BPAFG_DEMAND_INDEXES_SQL:
            cur.execute(idx)
        for stmt in PRIORITY_TEMPLATE_CREATE_SQL_SQLITE.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)
        for idx in PRIORITY_TEMPLATE_INDEXES_SQL:
            cur.execute(idx)
        conn.commit()
        logger.info(f"FIRA tables created in SQLite: {db_path}")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Query helpers (work with both psycopg2 and sqlite3 cursors)
# ---------------------------------------------------------------------------

def get_all_demand_data(cursor) -> list:
    """Fetch all demand rows."""
    cursor.execute("SELECT * FROM bpafg_demand ORDER BY project_name, dept_country, month")
    return cursor.fetchall()


def get_all_priority_data(cursor) -> list:
    """Fetch all priority template rows."""
    cursor.execute("SELECT * FROM priority_template ORDER BY priority, project, country")
    return cursor.fetchall()


def get_distinct_values(cursor, table: str, column: str) -> list:
    """Get distinct non-null values for a column."""
    cursor.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL ORDER BY {column}")
    return [row[0] for row in cursor.fetchall()]


def get_demand_aggregated(cursor, filters: dict = None) -> list:
    """
    Aggregate demand: SUM(value) grouped by project_name, dept_country, month.
    Optional filters: {column: value} pairs (value='All' is ignored).
    """
    where_clauses = []
    params = []
    if filters:
        for col, val in filters.items():
            if val and val != "All":
                where_clauses.append(f"{col} = %s")
                params.append(val)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    sql = f"""
        SELECT project_name, dept_country, month, SUM(value) as total_value
        FROM bpafg_demand
        {where_sql}
        GROUP BY project_name, dept_country, month
        ORDER BY project_name, dept_country, month
    """
    cursor.execute(sql, params)
    return cursor.fetchall()


def get_capacity_by_country(cursor) -> dict:
    """Return {country: target_capacity} from priority_template."""
    cursor.execute("""
        SELECT DISTINCT country, target_capacity, country_cost
        FROM priority_template
        WHERE country IS NOT NULL AND target_capacity IS NOT NULL
    """)
    result = {}
    for row in cursor.fetchall():
        country = row[0] if isinstance(row, (tuple, list)) else row["country"]
        cap = row[1] if isinstance(row, (tuple, list)) else row["target_capacity"]
        cost = row[2] if isinstance(row, (tuple, list)) else row["country_cost"]
        result[country] = {"target_capacity": float(cap or 0), "country_cost": float(cost or 0)}
    return result


def get_project_order(cursor) -> list:
    """Return ordered project list from priority_template."""
    cursor.execute("""
        SELECT DISTINCT project, priority
        FROM priority_template
        WHERE project IS NOT NULL AND project != ''
        ORDER BY priority ASC
    """)
    return [row[0] if isinstance(row, (tuple, list)) else row["project"] for row in cursor.fetchall()]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Quick test with SQLite
    setup_tables_sqlite()
    print("Tables created successfully in SQLite.")
