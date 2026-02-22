import argparse
import logging
from sqlalchemy import create_engine, text

# Import the DatabaseSetupManager
from db.setup_db import DatabaseSetupManager

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def clear_table_data(connection_string: str, table_name: str):
    """
    Connects to the database and removes all data from the specified table.

    Args:
        connection_string (str): The SQLAlchemy connection string.
        table_name (str): The name of the table to clear.
    """
    if not connection_string:
        raise ValueError("Connection string cannot be None or empty.")

    # Using TRUNCATE is faster than DELETE for clearing an entire table.
    # RESTART IDENTITY resets the auto-incrementing primary key.
    # CASCADE will drop data in tables with foreign-key references to this table.
    truncate_command = f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE;"

    logging.info(f"Connecting to database to clear data from: '{table_name}'...")
    try:
        engine = create_engine(connection_string)
        with engine.connect() as conn:
            with conn.begin():  # Start a transaction
                logging.warning(f"Executing: {truncate_command}")
                conn.execute(text(truncate_command))
            logging.info(f"✅ Successfully cleared all data from table '{table_name}'.")

    except Exception as e:
        logging.error(f"❌ An error occurred while clearing data from '{table_name}': {e}")
        raise

def main():
    """
    Main function to run the data clearing script.
    """
    parser = argparse.ArgumentParser(
        description="Clear data from database tables.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--config',
        type=str,
        default="config/config.yaml",
        help='Path to the configuration YAML file (default: config/config.yaml).'
    )
    parser.add_argument(
        '--table',
        type=str,
        default=None,
        help='Specific table to clear (e.g., opex_data_hybrid, langchain_pg_embedding). Overrides config default.'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Bypass the confirmation prompt. Use with caution.'
    )
    args = parser.parse_args()

    # --- Initialize Manager to get Configuration ---
    try:
        db_manager = DatabaseSetupManager(config_path=args.config)
        connection_string = db_manager._get_connection_string()
        
        # Determine Target Table
        # Priority: 1. CLI Argument, 2. Config 'table_name', 3. Fallback
        if args.table:
            target_table = args.table
        else:
            target_table = db_manager.schema_config.get("table_name", "opex_data_hybrid")

    except Exception as e:
        logging.error(f"Failed to initialize database configuration: {e}")
        return

    # --- Safety Check ---
    if not args.force:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("! WARNING: This is a destructive operation.                 !")
        print(f"! It will permanently delete all data from: '{target_table}'")
        if target_table == 'langchain_pg_collection':
             print("! (This will also cascade delete all associated embeddings)")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        
        confirm = input("Are you sure you want to continue? [y/N]: ")
        if confirm.lower() != 'y':
            logging.info("Operation cancelled by user.")
            return

    logging.info(f"--- Starting Data Clearing Process using '{args.config}' ---")

    try:
        # Perform the Clear Operation
        clear_table_data(connection_string, target_table)

    except Exception as e:
        logging.error("The data clearing process failed.")

if __name__ == "__main__":
    main()