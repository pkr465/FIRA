"""
FIRA — Drop all application tables from PostgreSQL.

Drops ALL FIRA tables in dependency-safe order:
  1. chat_messages      (FK → chat_sessions)
  2. chat_sessions
  3. opex_data_hybrid
  4. bpafg_demand
  5. priority_template
  6. headcount_data
  7. langchain_pg_embedding
  8. langchain_pg_collection

Usage:
    python db/drop_db.py                     # interactive confirmation
    python db/drop_db.py --force             # skip confirmation (automation)
    python db/drop_db.py --config path.yaml  # custom config
"""

import os
import sys
import argparse
import logging
import yaml
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# All FIRA tables in dependency-safe drop order
TARGET_TABLES = [
    "chat_messages",
    "chat_sessions",
    "opex_data_hybrid",
    "bpafg_demand",
    "priority_template",
    "headcount_data",
    "langchain_pg_embedding",
    "langchain_pg_collection",
]


def load_pg_config(config_path="config/config.yaml") -> dict:
    """Load Postgres ADMIN connection params from config.yaml."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    pg = cfg.get("Postgres", {})

    return {
        "host":     pg.get("host", "localhost"),
        "port":     int(pg.get("port", 5432)),
        "database": pg.get("database", "cnss_opex_db"),
        "user":     pg.get("admin_username", "postgres"),
        "password": pg.get("admin_password", "postgres"),
    }


def drop_tables(config_path="config/config.yaml", force=False):
    """Drop all FIRA application tables."""
    params = load_pg_config(config_path)
    logger.info(f"Connecting to {params['host']}:{params['port']}/{params['database']} as {params['user']}")

    conn = psycopg2.connect(**params)
    conn.autocommit = True

    try:
        cur = conn.cursor()

        # Safety confirmation
        if not force:
            print(f"\nWARNING: This will DROP the following tables from '{params['database']}':")
            for t in TARGET_TABLES:
                print(f"  - {t}")
            print("\nThis action is IRREVERSIBLE. All data and schema definitions will be lost.")
            confirm = input("Type 'DELETE' to confirm: ")
            if confirm != "DELETE":
                print("Operation cancelled.")
                return

        # Drop each table
        for table in TARGET_TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
            logger.info(f"  Dropped: {table}")

        logger.info("All FIRA tables dropped successfully.")
        print("\nNext steps:")
        print("  1. python bootstrap_db.py       # Recreate tables")
        print("  2. python main.py                # Re-ingest OpEx data")

    except Exception as e:
        logger.error(f"Drop failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FIRA — Drop all application tables.")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config.yaml")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()
    drop_tables(args.config, args.force)
