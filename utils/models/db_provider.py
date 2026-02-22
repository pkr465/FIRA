import logging
import time
from typing import Optional, Sequence, List, Dict, Any
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.sql import Select
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError, DisconnectionError
from sqlalchemy.dialects.postgresql import insert

# Import the Opex model defined in the previous step
# (Assumes the previous file was named models.py)
from utils.models.win_opex import WINOpexDataHybrid

logger = logging.getLogger(__name__)

class OpexDBProvider:
    """
    Database agent specifically for Opex Data Hybrid schema.
    Handles connection pooling, health checks, and Opex-specific queries.
    """

    def __init__(self, db_url: str):
        self.db_url = db_url
        logger.debug(f"Connecting to {self.db_url}")
        self._session: Optional[Session] = None
        self._engine = None
        self._Session = None
        self._last_health_check = 0
        self._health_check_interval_secs = 300
        self._initialize_connection()

    def _initialize_connection(self):
        """Initialize database connection with robust pooling and recycling settings"""
        try:
            # Create engine with comprehensive connection management
            self._engine = create_engine(
                self.db_url,
                pool_pre_ping=True,   # Validate connections before use
                pool_recycle=3600,    # Recycle connections after 1 hour
                pool_timeout=30,      # Timeout for getting connection from pool
                max_overflow=10,      # Allow up to 10 overflow connections
                pool_size=5,          # Base pool size
                echo=False,
            )
            self._Session = sessionmaker(bind=self._engine)
            self._session = self._Session()
            self._last_health_check = time.time()
            logger.debug(f"{self.__class__.__name__} initialized successfully.")
        except Exception as e:
            self._session = None
            self._engine = None
            self._Session = None
            logger.error(f"Failed to initialize {self.__class__.__name__}: {e}")

    def _is_connection_alive(self) -> bool:
        """Check if the database connection is still alive"""
        if not self._session or not self._engine:
            return False

        try:
            # Test the engine's connection pool first
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            # Then test the session
            self._session.execute(text("SELECT 1"))
            # logger.debug("Connection alive.") 
            return True
        except (OperationalError, DisconnectionError) as e:
            logger.warning(f"Database connection/engine is stale: {e}")
            return False
        except Exception as e:
            logger.warning(f"Unexpected error checking connection: {e}")
            return False

    def _refresh_connection(self):
        """Refresh the database connection"""
        logger.info(f"Refreshing database connection for {self.__class__.__name__}")

        # Close existing session if it exists
        if self._session:
            try:
                self._session.close()
            except Exception as e:
                logger.warning(f"Error closing existing session: {e}")

        # Dispose of existing engine if it exists
        if self._engine:
            try:
                self._engine.dispose()
            except Exception as e:
                logger.warning(f"Error disposing existing engine: {e}")

        # Reinitialize connection
        self._initialize_connection()

    def __del__(self):
        if self._session:
            try:
                self._session.close()
            except Exception:
                pass
        if self._engine:
            try:
                self._engine.dispose()
            except Exception:
                pass

    def _health_check(self):
        if not self._is_connection_alive():
            self._refresh_connection()
            if self._session is None:
                raise RuntimeError(f"Failed to refresh {self.__class__.__name__} session.")
        logger.info("Health check passed.")
        self._last_health_check = time.time()

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError(f"{self.__class__.__name__} session is not initialized.")

        if time.time() - self._last_health_check > self._health_check_interval_secs:
            self._health_check()

        return self._session

    def refresh_connection(self):
        """Manually refresh the database connection"""
        self._refresh_connection()

    # ==========================================
    # OPEX Specific Methods
    # ==========================================

    def get_total_record_count(self) -> int:
        """Returns the total number of rows in the Opex Hybrid table."""
        stmt = select(func.count()).select_from(WINOpexDataHybrid)
        return self.session.execute(stmt).scalar()

    def bulk_insert_records(self, records: List[Dict[str, Any]]):
        """
        Bulk inserts data extracted from Excel.
        Using PostgreSQL 'ON CONFLICT DO UPDATE' (Upsert) is recommended 
        if UUIDs might overlap, otherwise standard add_all is fine.
        """
        try:
            # Option A: Standard SQLAlchemy bulk insert (faster for pure inserts)
            self.session.bulk_insert_mappings(WINOpexDataHybrid, records)
            self.session.commit()
            logger.info(f"Successfully inserted {len(records)} records.")
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to bulk insert records: {e}")
            raise

    def get_by_uuids(self, uuids: List[str]) -> Sequence[WINOpexDataHybrid]:
        """
        Crucial for Hybrid Search:
        Retrieves full metadata rows based on UUIDs returned by the Vector DB.
        """
        if not uuids:
            return []
            
        stmt = select(WINOpexDataHybrid).where(WINOpexDataHybrid.uuid.in_(uuids))
        result = self.session.execute(stmt)
        return result.scalars().all()

    def execute_select(self, query: Select) -> Sequence:
        """Executes a generic select statement and returns scalar results."""
        result = self.session.execute(query)
        return result.scalars().all()