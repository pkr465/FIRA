import logging
import os
import yaml
from sqlalchemy import create_engine, text, inspect
from typing import Dict, Optional

# --- IMPORT SCHEMA CONFIG ---
from config.schema_config import SCHEMA_CONFIG

class DatabaseSetupManager:
    """
    Manages database connection, schema setup, and migrations (adding missing columns).
    """
    
    def __init__(self, config_path: str = 'config/config.yaml', schema_config: Dict = SCHEMA_CONFIG):
        self.config_path = config_path
        self.schema_config = schema_config
        self.logger = self._configure_logger()
        self.config = self._load_config()

        # Extract Vector Config (Defaults to 'vector' and 768 dim if not in schema)
        vec_cfg = self.schema_config.get("vector_config", {})
        self.vector_col = vec_cfg.get("column_name", "vector")
        self.vector_dim = vec_cfg.get("dimension", 1024)

    def _configure_logger(self) -> logging.Logger:
        logger = logging.getLogger(__name__)
        if not logger.hasHandlers():
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        return logger

    def _load_config(self) -> Dict:
        try:
            if not os.path.exists(self.config_path):
                raise FileNotFoundError(f"Configuration file not found at: {self.config_path}")
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            raise

    def _get_connection_string(self) -> str:
        """Build SQLAlchemy connection string from config.yaml (app user)."""
        try:
            pg_config = self.config.get('Postgres')
            if not pg_config:
                raise KeyError("Could not find 'Postgres' section in config.")

            username = pg_config.get('username', 'fira_user')
            password = pg_config.get('password', 'fira_password')
            host     = pg_config.get('host', 'localhost')
            port     = int(pg_config.get('port', 5432))
            database = pg_config.get('database', 'cnss_opex_db')

            return f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}"

        except KeyError as e:
            self.logger.error(f"Configuration is missing a required key: {e}")
            raise

    def setup_database(self) -> None:
        """
        Ensures the table and required columns exist.
        - Creates table if missing.
        - Adds 'vector' column if table exists but column is missing.
        """
        connection_string = self._get_connection_string()
        table_name = self.schema_config.get("table_name", "opex_data_hybrid")
        
        try:
            engine = create_engine(connection_string)
            inspector = inspect(engine)

            with engine.connect() as conn:
                with conn.begin(): # Start Transaction
                    
                    # 1. Enable Vector Extension (Crucial)
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

                    # 2. Check if Table Exists
                    if inspector.has_table(table_name):
                        self.logger.info(f"✅ Table '{table_name}' exists. Checking schema...")
                        
                        # --- MIGRATION LOGIC: Check for missing Vector Column ---
                        existing_columns = [col['name'] for col in inspector.get_columns(table_name)]
                        
                        if self.vector_col not in existing_columns:
                            self.logger.warning(f"⚠️ Column '{self.vector_col}' missing in '{table_name}'. Adding it now...")
                            
                            # Add Column
                            alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {self.vector_col} vector({self.vector_dim})"
                            conn.execute(text(alter_sql))
                            self.logger.info(f"✅ Added column '{self.vector_col}'.")
                            
                            # Add Index for the new column
                            idx_sql = f"CREATE INDEX IF NOT EXISTS {table_name}_vec_idx ON {table_name} USING ivfflat ({self.vector_col} vector_cosine_ops) WITH (lists = 100)"
                            conn.execute(text(idx_sql))
                            self.logger.info("✅ Created vector index.")
                        else:
                            self.logger.info(f"✅ Column '{self.vector_col}' already exists.")

                    else:
                        # 3. Create Table (Fresh Setup)
                        self.logger.info(f"Table '{table_name}' not found. Creating...")
                        conn.execute(text(self.schema_config["create_table_sql"]))
                        self.logger.info(f"✅ Table '{table_name}' created.")

                        self.logger.info(f"Applying indexes...")
                        for index_sql in self.schema_config["indexes_sql"]:
                            try:
                                conn.execute(text(index_sql))
                            except Exception as idx_err:
                                self.logger.warning(f"Index creation note: {idx_err}")
                        
                    self.logger.info(f"🎉 Database setup for '{table_name}' completed.")

        except Exception as e:
            self.logger.error(f"❌ Database setup failed: {e}", exc_info=True)
            raise

def main():
    try:
        db_manager = DatabaseSetupManager()
        db_manager.setup_database()
    except Exception as e:
        logging.error(f"Setup failed: {e}")

if __name__ == "__main__":
    main()