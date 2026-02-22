import argparse
import logging
import pandas as pd
from sqlalchemy import create_engine, inspect, text

# Import the DatabaseSetupManager
from db.setup_db import DatabaseSetupManager

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

def list_table_contents(connection_string: str, table_name: str, limit: int = 20, show_all: bool = False):
    """
    Connects to the database and prints table contents.
    Includes special handling for 'langchain_pg_embedding' to make it readable.
    """
    if not connection_string:
        raise ValueError("Connection string cannot be empty.")

    engine = create_engine(connection_string)
    inspector = inspect(engine)

    # 1. Verify Table Exists
    if not inspector.has_table(table_name):
        logging.error(f"❌ Table '{table_name}' does not exist in the database.")
        print(f"Available tables: {inspector.get_table_names()}")
        return

    # 2. Construct Query
    # Special handling for Vector Store table to avoid dumping huge vector arrays
    if table_name == "langchain_pg_embedding":
        logging.info("ℹ️  Detected Vector Store table. Excluding raw vector column for readability.")
        # Join with collection table to show readable Collection Name instead of Collection UUID
        query = f"""
            SELECT 
                e.id, 
                c.name as collection_name, 
                LEFT(e.document, 100) as document_snippet, 
                e.cmetadata 
            FROM langchain_pg_embedding e
            LEFT JOIN langchain_pg_collection c ON e.collection_id = c.uuid
            ORDER BY e.id
        """
    else:
        # Generic query for other tables (like opex_data_hybrid)
        query = f"SELECT * FROM {table_name}"
        # Add basic ordering if 'id' exists to ensure consistent display
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        if 'id' in columns:
            query += " ORDER BY id"

    # Apply Limits
    if not show_all:
        query += f" LIMIT {limit}"

    logging.info(f"Connecting to database to fetch rows from '{table_name}'...")

    try:
        # 3. Fetch and Display
        df = pd.read_sql_query(text(query), engine)

        if df.empty:
            print(f"\n--- The table '{table_name}' is empty. ---\n")
        else:
            print(f"\n--- Contents of '{table_name}' ---")
            
            # formatting: ensure text doesn't get cut off too aggressively in the console
            pd.set_option('display.max_colwidth', 50) 
            pd.set_option('display.max_columns', None)
            pd.set_option('display.width', 1000)

            print(df.to_string(index=False))
            print(f"\nDisplayed {len(df)} row(s).")
            
            if not show_all and len(df) == limit:
                 print(f"Note: Query was limited to {limit} rows. Use --all to see the full table.")

    except Exception as e:
        logging.error(f"❌ Error fetching data: {e}")
        raise

def main():
    parser = argparse.ArgumentParser(description="List database table contents.")
    parser.add_argument('--config', type=str, default="config/config.yaml", help='Path to config file.')
    parser.add_argument('--table', type=str, default=None, help='Specific table to list (overrides config).')
    parser.add_argument('--limit', type=int, default=20, help='Max rows to display.')
    parser.add_argument('--all', action='store_true', help='Display all rows.')
    
    args = parser.parse_args()

    try:
        # Initialize Manager
        db_manager = DatabaseSetupManager(config_path=args.config)
        connection_string = db_manager._get_connection_string()
        
        # Determine which table to list
        # Priority: 1. CLI Argument, 2. 'table_name' in config, 3. Default to 'opex_data_hybrid'
        if args.table:
            target_table = args.table
        else:
            # Default fallback if config doesn't specify a valid SQL table
            target_table = db_manager.schema_config.get("table_name", "opex_data_hybrid")
            
            # Config often points to a Collection Name (not a Table Name) for vectors.
            # If the config name looks like a collection, we default to the actual vector table.
            # (Simple heuristic: if it's not the hybrid table, check if it's the vector table)
            if target_table not in ["opex_data_hybrid", "langchain_pg_embedding"]:
                # If config has "opex_vectors" (collection name), we probably want to see the embedding table
                logging.info(f"Config table name '{target_table}' might be a collection. Defaulting to 'langchain_pg_embedding'.")
                target_table = "langchain_pg_embedding"

        list_table_contents(
            connection_string=connection_string, 
            table_name=target_table,
            limit=args.limit,
            show_all=args.all
        )

    except Exception as e:
        logging.error(f"Failed: {e}")

if __name__ == "__main__":
    main()