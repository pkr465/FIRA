import yaml
import logging
import os
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy import Integer, String, Text, Numeric, BigInteger, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy.sql import func

# ==============================================================================
# SCHEMA CONFIGURATION LOADER
# ==============================================================================

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_schema_from_yaml(schema_path: str = 'config/schema.yaml') -> dict:
    """
    Loads a schema definition from a YAML file.
    Returns a dictionary containing the configuration (e.g., table_name).
    """
    try:
        logging.info(f"Loading schema definition from '{schema_path}'...")
        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"Schema file not found at the specified path: {schema_path}")

        with open(schema_path, 'r') as f:
            raw_config = yaml.safe_load(f)

        table_name = raw_config['table_name']

        # Format SQL templates (optional, kept for compatibility with user provided logic)
        create_sql = raw_config.get('create_table_sql', '').format(table_name=table_name)
        indexes_sql = [
            index.format(table_name=table_name) for index in raw_config.get('indexes_sql', [])
        ]

        schema_config = {
            "table_name": table_name,
            "create_table_sql": create_sql,
            "indexes_sql": indexes_sql
        }
        logging.info(f"✅ Schema for table '{table_name}' loaded successfully.")
        return schema_config

    except (KeyError, TypeError) as e:
        logging.error(f"Schema file '{schema_path}' is missing a required key or is malformed: {e}")
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading the schema: {e}")
        raise

# Load configuration dynamically
# Note: This requires 'config/schema.yaml' to exist in the working directory
try:
    SCHEMA_CONFIG = load_schema_from_yaml()
    TABLE_NAME = SCHEMA_CONFIG['table_name']
except Exception as e:
    logging.warning(f"Could not load schema config: {e}. Defaulting table name to 'opex_data_hybrid'.")
    TABLE_NAME = 'opex_data_hybrid'


# ==============================================================================
# SQLALCHEMY MODEL
# ==============================================================================

Base = declarative_base()

class WINOpexDataHybrid(Base):
    """
    SQLAlchemy model that dynamically sets its table name based on config/schema.yaml.
    """
    __tablename__ = TABLE_NAME

    # === Primary Key ===
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # === Linkage ID (Critical for Hybrid Search) ===
    # Using UUID as per schema definition
    uuid: Mapped[str] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)

    # === Source Metadata ===
    source_file: Mapped[Optional[str]] = mapped_column(Text)
    source_sheet: Mapped[Optional[str]] = mapped_column(Text)

    # === Promoted Columns (Matching schema definition) ===
    fiscal_year: Mapped[Optional[int]] = mapped_column(Integer)
    project_number: Mapped[Optional[int]] = mapped_column(BigInteger)
    dept_lead: Mapped[Optional[str]] = mapped_column(Text)
    hw_sw: Mapped[Optional[str]] = mapped_column(Text)
    
    # Dollar columns — from $Data sheet: TM1 ($'M) and ODS ($'M)
    tm1_m: Mapped[Optional[float]] = mapped_column(Numeric(18, 6))
    ods_m: Mapped[Optional[float]] = mapped_column(Numeric(18, 6))
    # Man-month columns — from MM Data sheet: TM1 MM and ODS MM
    tm1_mm: Mapped[Optional[float]] = mapped_column(Numeric(18, 6))
    ods_mm: Mapped[Optional[float]] = mapped_column(Numeric(18, 6))

    # === JSONB bucket ===
    additional_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)

    # === Timestamps ===
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now(),
        nullable=False
    )

    # === Indexes ===
    # We dynamically name indexes based on the table name to ensure uniqueness/consistency
    __table_args__ = (
        Index(f'idx_{TABLE_NAME}_uuid', 'uuid'),
        Index(f'idx_{TABLE_NAME}_fiscal_year', 'fiscal_year'),
        Index(f'idx_{TABLE_NAME}_project_number', 'project_number'),
        Index(f'idx_{TABLE_NAME}_dept_lead', 'dept_lead'),
        Index(f'idx_{TABLE_NAME}_hw_sw', 'hw_sw'),
        Index(f'idx_{TABLE_NAME}_additional_data', 'additional_data', postgresql_using='gin'),
    )

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}(id={self.id}, uuid='{self.uuid}', "
            f"fiscal_year={self.fiscal_year}, project={self.project_number})>"
        )