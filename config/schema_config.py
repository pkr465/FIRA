# ==============================================================================
# SCHEMA CONFIGURATION LOADER
#
# This script loads the schema definition from 'config/schema.yaml',
# formats the SQL statements with the correct table name, and exports a
# single SCHEMA_CONFIG dictionary for use by other modules.
# ==============================================================================

import yaml
import logging
import os

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_schema_from_yaml(schema_path: str = 'config/schema.yaml') -> dict:
    """
    Loads a schema definition from a YAML file, formats the SQL statements,
    and returns it as a final configuration dictionary.

    It replaces all instances of '{table_name}' in the SQL strings.

    Args:
        schema_path (str): The path to the schema YAML file.

    Returns:
        dict: A dictionary containing the fully-formed schema configuration.
              e.g., {"table_name": "...", "create_table_sql": "...", "indexes_sql": [...], "schema_map": {...}}

    Raises:
        FileNotFoundError: If the schema YAML file cannot be found.
        KeyError: If the YAML file is missing a required key.
    """
    try:
        logging.info(f"Loading schema definition from '{schema_path}'...")
        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"Schema file not found at the specified path: {schema_path}")

        with open(schema_path, 'r') as f:
            raw_config = yaml.safe_load(f)

        table_name = raw_config['table_name']

        # Use .format() to inject the table name into the SQL templates from the YAML file
        create_sql = raw_config['create_table_sql'].format(table_name=table_name)
        indexes_sql = [
            index.format(table_name=table_name) for index in raw_config['indexes_sql']
        ]
        
        # Extract the schema map
        schema_map = raw_config.get('schema_map', {})

        # Assemble the final, ready-to-use config object
        schema_config = {
            "table_name": table_name,
            "create_table_sql": create_sql,
            "indexes_sql": indexes_sql,
            "schema_map": schema_map,
            "vector_config": raw_config.get('vector_config', {})
        }
        logging.info(f"✅ Schema for table '{table_name}' loaded and formatted successfully.")
        return schema_config

    except (KeyError, TypeError) as e:
        logging.error(f"Schema file '{schema_path}' is missing a required key or is malformed: {e}")
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading the schema: {e}")
        raise

# --- Main Export ---
# Load the schema configuration when this module is imported.
# Other scripts (like setup_db.py or main.py) will import this SCHEMA_CONFIG variable.
SCHEMA_CONFIG = load_schema_from_yaml()