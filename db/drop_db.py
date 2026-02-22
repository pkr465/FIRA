import psycopg2
import yaml
import argparse
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# List of tables to drop (Order matters if not using CASCADE, but we will use CASCADE)
# 1. opex_data_hybrid (Your custom data)
# 2. langchain_pg_embedding (Vector data)
# 3. langchain_pg_collection (Vector collections)
TARGET_TABLES = [
    "opex_data_hybrid",
    "langchain_pg_embedding",
    "langchain_pg_collection"
]

def load_config(config_path="config/config.yaml"):
    """Load database configuration from YAML."""
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config file: {e}")
        sys.exit(1)

def get_db_connection(config):
    """Establish connection to PostgreSQL."""
    try:
        db_cfg = config.get("database", {})
        conn = psycopg2.connect(
            host=db_cfg.get("host", "localhost"),
            port=db_cfg.get("port", 5432),
            database=db_cfg.get("dbname", "postgres"),
            user=db_cfg.get("user", "postgres"),
            password=db_cfg.get("password", "")
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

def drop_tables(config_path, force=False):
    config = load_config(config_path)
    conn = get_db_connection(config)
    
    try:
        cur = conn.cursor()
        
        # 1. Safety Check
        if not force:
            print("\nWARNING: This will DROP (delete) the following tables:")
            for t in TARGET_TABLES:
                print(f"  - {t}")
            print("\nThis action is irreversible. All data and schema definitions will be lost.")
            confirm = input("Type 'DELETE' to confirm: ")
            if confirm != "DELETE":
                print("Operation cancelled.")
                return

        # 2. Execution
        for table in TARGET_TABLES:
            logger.info(f"Dropping table: {table}...")
            # CASCADE ensures that if a table depends on this one, it is also dropped/handled
            cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
            print("🗑️  Dropping stale table 'opex_data_hybrid'...")
            cur.execute("DROP TABLE IF EXISTS opex_data_hybrid CASCADE;")
            print("✅ Table dropped. You can now run main.py.")
        
        conn.commit()
        logger.info("Successfully dropped all specified tables.")
        
    except Exception as e:
        logger.error(f"An error occurred during drop: {e}")
        conn.rollback()
    finally:
        conn.close()



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Drop application tables from PostgreSQL.")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config.yaml")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    
    args = parser.parse_args()

    drop_tables(args.config, args.force)
   