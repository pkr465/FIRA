import logging
import os
import yaml
from typing import Optional, List, Any
from sqlalchemy import select, distinct, text

# Import the base provider
try:
    from utils.models.db_provider import OpexDBProvider
except ImportError:
    # Fallback for local testing if path differs
    from db_provider import OpexDBProvider

# Import your Opex Model
try:
    from utils.models.win_opex import WINOpexDataHybrid
except ImportError:
    from win_opex import WINOpexDataHybrid

logger = logging.getLogger(__name__)

class OpexHybridProvider(OpexDBProvider):
    """
    Singleton Wrapper for the Opex Database.
    Ensures only one connection pool exists and handles specific business logic.
    """
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OpexHybridProvider, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Prevent re-initialization if already initialized
        if self._initialized:
            return

        db_url = self._get_db_url()
        
        # Initialize the Parent (OpexDBProvider) logic
        # This typically initializes self.session (scoped_session) and self.engine (Engine)
        super().__init__(db_url)
        self._initialized = True

    def _get_db_url(self) -> str:
        """
        Attempts to resolve the Database URL from the unified Config object.
        """
        # 1. Try Unified Config Object
        try:
            from config.config import Config
            
            # Check if critical credentials exist in the loaded Config
            if Config.POSTGRES_USER and Config.POSTGRES_DB_NAME:
                logger.info("Loaded DB credentials from Config.")
                return (
                    f"postgresql+psycopg2://{Config.POSTGRES_USER}:{Config.POSTGRES_PWD}"
                    f"@{Config.POSTGRES_HOST}:{Config.POSTGRES_PORT}/{Config.POSTGRES_DB_NAME}"
                )
        except ImportError:
            logger.debug("Could not import config.config module. Falling back.")

        # 2. Fallback: Try loading yaml files directly (if Config class import failed)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.abspath(os.path.join(current_dir, "../../"))
        
        candidates = [
            os.path.join(root_dir, "config", "config.yaml"),
            "config/config.yaml",
            "config.yaml"
        ]

        for path in candidates:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        data = yaml.safe_load(f)
                        if data and ("postgres" in data or "database" in data):
                             # Fallback extraction logic
                            cfg = data.get("postgres") or data.get("database")
                            return (
                                f"postgresql+psycopg2://{cfg.get('username') or cfg.get('user')}:{cfg.get('password')}"
                                f"@{cfg.get('host', 'localhost')}:{cfg.get('port', 5432)}/{cfg.get('database') or cfg.get('dbname')}"
                            )
                except Exception as e:
                    logger.warning(f"Failed to read fallback config {path}: {e}")

        # 3. Environment Variable Fallback
        env_url = os.getenv("OPEX_DB_URL")
        if env_url:
            return env_url
            
        # 4. Final Fallback
        logger.warning("No DB config found. Using default placeholder.")
        return "postgresql+psycopg2://user:pass@localhost:5432/opex_db"

    # ==========================================
    # MISSING PROPERTIES FIXED HERE
    # ==========================================

    @property
    def engine(self):
        """
        Expose the SQLAlchemy engine. 
        Required by summary.py for pandas.read_sql
        """
        # If parent class exposes engine, use it
        if hasattr(super(), 'engine'):
            return super().engine
        
        # If parent stored it as _engine
        if hasattr(self, '_engine'):
            return self._engine
            
        # Fallback: retrieve from session binding
        if hasattr(self, 'session'):
            return self.session.get_bind()
            
        raise AttributeError("Database engine not initialized")

    def SessionLocal(self):
        """
        Provide a session factory-like interface.
        Required by chat_persistence.py for 'with self.db.SessionLocal() as session:'
        """
        # If self.session is a scoped_session, calling it returns a thread-local session
        # If it is a Session instance, returning it directly works for simple cases,
        # but for thread safety in persistence, we rely on the parent's implementation.
        return self.session

    # ==========================================
    # AGENT SUPPORT METHODS
    # ==========================================

    def execute_sql_query(self, sql: str, format_as_markdown: bool = False) -> Any:
        """
        Executes a raw SQL query safely and returns the results.
        """
        try:
            stmt = text(sql)
            result = self.session.execute(stmt)
            
            if result.returns_rows:
                keys = list(result.keys())
                rows = [dict(zip(keys, row)) for row in result.fetchall()]
            else:
                return "Query executed successfully (No rows returned)."

            if format_as_markdown:
                if not rows:
                    return "No results found."
                
                header = "| " + " | ".join(keys) + " |"
                separator = "| " + " | ".join(["---"] * len(keys)) + " |"
                body = ""
                for row in rows:
                    row_vals = [str(row.get(k, "")).replace("\n", " ") for k in keys]
                    body += "\n| " + " | ".join(row_vals) + " |"
                
                return f"{header}\n{separator}{body}"
            
            return rows

        except Exception as e:
            if "OperationalError" in str(e) or "connection" in str(e).lower():
                logger.critical(f"Database Connection Error: {e}")
            else:
                logger.error(f"SQL Execution Failed: {e}")
            raise e

    # ==========================================
    # OPEX Business Logic
    # ==========================================

    def get_record_by_uuid(self, uuid: str) -> Optional[WINOpexDataHybrid]:
        return self.session.get(WINOpexDataHybrid, uuid)

    def get_projects_by_fiscal_year(self, fiscal_year: str) -> List[WINOpexDataHybrid]:
        stmt = select(WINOpexDataHybrid).where(WINOpexDataHybrid.fiscal_year == fiscal_year)
        result = self.session.execute(stmt)
        return result.scalars().all()

    def get_unique_project_numbers(self) -> List[str]:
        stmt = select(distinct(WINOpexDataHybrid.project_number))
        result = self.session.execute(stmt)
        return [row[0] for row in result.all() if row[0] is not None]

    def get_latest_entry_fiscal_year(self) -> str:
        stmt = select(WINOpexDataHybrid.fiscal_year).order_by(WINOpexDataHybrid.fiscal_year.desc()).limit(1)
        return self.session.execute(stmt).scalar() or "Unknown"

    def get_records_by_uuids(self, uuids: List[str]) -> List[WINOpexDataHybrid]:
        if not uuids:
            return []
        if hasattr(super(), 'get_by_uuids'):
            return super().get_by_uuids(uuids)
        stmt = select(WINOpexDataHybrid).where(WINOpexDataHybrid.uuid.in_(uuids))
        return self.session.execute(stmt).scalars().all()

# Instantiate the singleton
OpexDB = OpexHybridProvider()