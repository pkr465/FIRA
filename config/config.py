import os
import json
import logging
import socket
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union, List, Any
from dotenv import load_dotenv, find_dotenv
from urllib.parse import quote

logger = logging.getLogger(__name__)

@dataclass
class _Config:
    """
    Unified configuration class that loads settings from config.yaml first,
    then overrides with environment variables (.env).
    """

    # --- 1. Path Settings ---
    SOURCE_PATH: Optional[Path] = None       # ../files/opex  (OpEx Excel files)
    RESOURCE_PATH: Optional[Path] = None     # ../files/resource  (FIRA resource planner CSVs)
    SAVE_PATH: Optional[Path] = None
    TASK_PATH: Optional[Path] = None
    GT_PATH: Optional[Path] = None
    OUT_PATH: Optional[Path] = None
    OUTPUT_JSONL_PATH: Optional[Path] = None

    # --- 2. Excel Settings ---
    # Updated to handle a list of file names from the 'file_names' key
    EXCEL_FILE_NAMES: List[str] = field(default_factory=list)

    # --- 3. Worker Settings ---
    WORKER: int = 1
    REPEAT: int = 1

    # --- 4. Agent Settings ---
    AGENT_API_BACKEND: str = "xw"
    AGENT_APP_BACKEND: str = "excel"
    AGENT_PROMPT_PATH: Optional[Path] = None
    AGENT_API_DOC_PATH: Optional[Path] = None
    USE_DOC_IN_SYSPROMPT: bool = True
    USE_EXT_DOC: bool = True
    USE_SAME_LLM: bool = True
    USE_ORACLE_API_DOC: bool = False
    ADD_EXAMPLE_DATA2FEEDBACK: bool = False
    MAX_CYCLE_TIMES: int = 20
    MAX_ERROR_COUNT: int = 999

    # --- 5. QGenie Settings ---
    QGENIE_API_KEY: Optional[str] = None
    QGENIE_MODEL_NAME: str = "qgenie"
    CODING_MODEL_NAME: str = None
    REASONING_MODEL_NAME: str = None
    QGENIE_CHAT_ENDPOINT: Optional[str] = None

    # --- 6. Model Specific Settings ---
    ANTHROPIC_MODEL: Optional[str] = None
    AZURE_MODEL: Optional[str] = None
    GEMINI_MODEL: Optional[str] = None

    # --- 7. Database & Postgres ---
    DATABASE_NAME: str = "Postgres"
    POSTGRES_CONNECTION: Optional[str] = None
    POSTGRES_ADMIN_USER: Optional[str] = None
    POSTGRES_ADMIN_PWD: Optional[str] = None
    POSTGRES_COLLECTION: Optional[str] = None
    POSTGRES_COLLECTION_TABLENAME: Optional[str] = None
    POSTGRES_EMBEDDING_TABLENAME: Optional[str] = None
    POSTGRES_HYBRID_TABLENAME: Optional[str] = None
    POSTGRES_STORE_NAME: Optional[str] = None
    POSTGRES_USER: Optional[str] = None
    POSTGRES_DB_NAME: Optional[str] = None
    POSTGRES_PWD: Optional[str] = None
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # --- 8. Legacy/Environment Specific Defaults ---
    OBJECT_STORAGE_DIR: Path = field(default_factory=lambda: Path("./storage"))
    OBJECT_STORAGE_BASE_URL: Optional[str] = "localhost:8000"
    STREAMLIT_HOSTNAME: str = field(default=socket.gethostname())
    STREAMLIT_PORT: int = 8502
    LOG_LEVEL: str = "INFO"
    FEEDBACK_EMAIL_ID: str = "pavanr@qti.qualcomm.com"
    

    # Private field to track initialization
    _initialized: bool = field(default=False, init=False)

    def __post_init__(self):
        """Initialize configuration: YAML -> Env Vars -> Validation"""
        if not self._initialized:
            # 1. Load YAML (Base Config)
            self._load_yaml_configuration()
            
            # 2. Load Env (Overrides)
            self._load_env_files()
            self._load_from_environment()
            
            self._initialized = True

    def _load_yaml_configuration(self, yaml_file: str = "config.yaml"):
        """Loads config.yaml and maps nested keys to class attributes."""
        if not os.path.exists(yaml_file):
            # Try looking in config/ folder if not in root
            yaml_file = f"config/{yaml_file}"
            if not os.path.exists(yaml_file):
                logger.warning(f"Config YAML not found at {yaml_file}. Using defaults/env vars.")
                return

        logger.info(f"Loading configuration from {yaml_file}")
        try:
            with open(yaml_file, 'r') as f:
                data = yaml.safe_load(f)
            
            if not data:
                return

            # Define Mapping: (YAML Section, YAML Key) -> Class Attribute
            # If YAML Section is None, it looks in the root of the YAML
            mapping = [
                # Path Section
                (('Path', 'source_path'), 'SOURCE_PATH'),
                (('Path', 'resource_path'), 'RESOURCE_PATH'),
                (('Path', 'save_path'), 'SAVE_PATH'),
                (('Path', 'task_path'), 'TASK_PATH'),
                (('Path', 'gt_path'), 'GT_PATH'),
                (('Path', 'out_path'), 'OUT_PATH'),
                (('Path', 'output_jsonl_path'), 'OUTPUT_JSONL_PATH'),
                
                # Excel Section
                # CHANGED: Mapping 'file_names' (comma separated in yaml) to 'EXCEL_FILE_NAMES' (List)
                (('Excel', 'file_names'), 'EXCEL_FILE_NAMES'),
                
                # Root Settings
                ((None, 'worker'), 'WORKER'),
                ((None, 'repeat'), 'REPEAT'),
                
                # Agent Section
                (('Agent', 'API_backend'), 'AGENT_API_BACKEND'),
                (('Agent', 'APP_backend'), 'AGENT_APP_BACKEND'),
                (('Agent', 'prompt_path'), 'AGENT_PROMPT_PATH'),
                (('Agent', 'api_doc_path'), 'AGENT_API_DOC_PATH'),
                (('Agent', 'use_doc_in_syspromt'), 'USE_DOC_IN_SYSPROMPT'),
                (('Agent', 'use_ext_doc'), 'USE_EXT_DOC'),
                (('Agent', 'use_same_LLM'), 'USE_SAME_LLM'),
                (('Agent', 'use_oracle_API_doc'), 'USE_ORACLE_API_DOC'),
                (('Agent', 'add_example_data2feedback'), 'ADD_EXAMPLE_DATA2FEEDBACK'),
                (('Agent', 'max_cycle_times'), 'MAX_CYCLE_TIMES'),
                (('Agent', 'max_error_count'), 'MAX_ERROR_COUNT'),
                
                # QGenie Section
                # NOTE: api_key is intentionally NOT mapped from YAML — it must come from .env
                (('Qgenie', 'model_name'), 'QGENIE_MODEL_NAME'),
                (('Qgenie', 'coding_model_name'), 'CODING_MODEL_NAME'),
                (('Qgenie', 'reasoning_model_name'), 'REASONING_MODEL_NAME'),
                (('Qgenie', 'chat_endpoint'), 'QGENIE_CHAT_ENDPOINT'),
                
                # Other Models
                (('Anthropic', 'model_name'), 'ANTHROPIC_MODEL'),
                (('Azure', 'model_name'), 'AZURE_MODEL'),
                (('Gemini', 'model_name'), 'GEMINI_MODEL'),
                
                # Database
                (('Database', 'database_name'), 'DATABASE_NAME'),
                
                # Postgres Section — all values come from config.yaml
                (('Postgres', 'connection'), 'POSTGRES_CONNECTION'),
                (('Postgres', 'admin_username'), 'POSTGRES_ADMIN_USER'),
                (('Postgres', 'admin_password'), 'POSTGRES_ADMIN_PWD'),
                (('Postgres', 'collection'), 'POSTGRES_COLLECTION'),
                (('Postgres', 'collection_tablename'), 'POSTGRES_COLLECTION_TABLENAME'),
                (('Postgres', 'embedding_tablename'), 'POSTGRES_EMBEDDING_TABLENAME'),
                (('Postgres', 'store_name'), 'POSTGRES_STORE_NAME'),
                (('Postgres', 'username'), 'POSTGRES_USER'),
                (('Postgres', 'database'), 'POSTGRES_DB_NAME'),
                (('Postgres', 'password'), 'POSTGRES_PWD'),
                (('Postgres', 'host'), 'POSTGRES_HOST'),
                (('Postgres', 'port'), 'POSTGRES_PORT'),
                # NOTE: Postgres passwords are now in config.yaml directly.
                # The env-var override still works if someone sets POSTGRES_PWD etc.

                # Streamlit Section
                (('Streamlit', 'port'), 'STREAMLIT_PORT'),

                # Feedback Section
                (('Feedback', 'email_id'), 'FEEDBACK_EMAIL_ID'),
            ]

            for (section, key), attr_name in mapping:
                val = None
                if section:
                    if section in data and key in data[section]:
                        val = data[section][key]
                else:
                    # Root level
                    if key in data:
                        val = data[key]
                
                if val is not None:
                    # Apply conversion logic using existing helper
                    field_type = self.__dataclass_fields__[attr_name].type
                    converted_val = self._convert_value(str(val), field_type, attr_name)
                    setattr(self, attr_name, converted_val)

        except Exception as e:
            logger.error(f"Error loading config.yaml: {e}")

    def _load_env_files(self):
        """Load environment variables from default.env and .env files."""
        load_order = [".default.env", ".env"]
        for env_file in load_order:
            env_path = find_dotenv(env_file)
            if env_path:
                load_dotenv(env_file, override=True)

    def _load_from_environment(self):
        """Load values from environment variables and apply type conversions."""
        for field_name, field_info in self.__dataclass_fields__.items():
            if field_name.startswith("_"): continue

            env_value = os.getenv(field_name)
            if env_value is not None:
                env_value = self._strip_quotes(env_value)
                field_type = field_info.type
                converted_value = self._convert_value(env_value, field_type, field_name)
                setattr(self, field_name, converted_value)

    def _convert_value(self, value: str, field_type: type, field_name: str) -> Any:
        """Convert string value to appropriate type based on field annotation."""
        if hasattr(field_type, "__origin__") and field_type.__origin__ is Union:
            non_none_types = [t for t in field_type.__args__ if t is not type(None)]
            if non_none_types:
                field_type = non_none_types[0]

        try:
            if field_type == int:
                return int(value)
            elif field_type == Path or field_type == Optional[Path]:
                return Path(str(value)).expanduser()
            elif field_type == bool:
                if isinstance(value, bool): return value
                return str(value).lower() in ("true", "1", "yes", "on")
            elif hasattr(field_type, "__origin__") and field_type.__origin__ is list:
                # Handle comma-separated strings for List types
                if isinstance(value, list): return value
                items = [item.strip() for item in str(value).split(",")]
                return [item for item in items if item]
            else:
                return value
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not convert {field_name}='{value}' to {field_type}: {e}")
            return value

    @staticmethod
    def _strip_quotes(value: str) -> str:
        if isinstance(value, str):
            return value.strip("'\"")
        return value

    def dumps(self) -> str:
        """Return configuration settings as a string in .env file format."""
        lines = []
        for field_name, field_info in self.__dataclass_fields__.items():
            if field_name.startswith("_"): continue
            value = getattr(self, field_name)
            if value is None: continue
            
            env_value = str(value)
            if " " in env_value or any(char in env_value for char in ['$', '"', "'", '\\']):
                env_value = '"' + env_value.replace('"', '\\"') + '"'
            lines.append(f"{field_name}={env_value}")
        return "\n".join(lines)

# Singleton instance
_config_instance: Optional[_Config] = None

def get_config() -> _Config:
    global _config_instance
    if _config_instance is None:
        _config_instance = _Config()
    return _config_instance

Config = get_config()
__all__ = ["Config", "get_config"]
