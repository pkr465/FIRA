import json
import uuid
import logging
import argparse
import sys
from typing import List, Dict, Any

# Import our custom modules
from db.vector_store import PostgresVectorStore
from db.embedding_client import EmbeddingClient
from db.setup_db import DatabaseSetupManager
from langchain_core.documents import Document

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DataIngestionAgent:
    def __init__(self, config_path="config.yaml"):
        
        self.config_path = config_path
        
        # 1. Setup Database Connection String
        self.db_manager = DatabaseSetupManager(config_path=config_path)
        self.connection_string = self.db_manager._get_connection_string()
        
        # 2. Initialize Embeddings (QGenie)
        self.embed_client = EmbeddingClient()
        self.embeddings = self.embed_client.get_embedding_function() 
        
        # 3. Initialize Vector Store
        # UPDATED: Removed 'collection_name'. The store now reads the table name 
        # directly from config/schema.yaml (default: 'opex_data_hybrid').
        self.vector_store = PostgresVectorStore(
            connection_string=self.connection_string,
            embedding_function=self.embeddings
        )

    def generate_deterministic_uuid(self, content: str) -> str:
        """
        Generates a UUID based on the content hash. 
        Same content = Same UUID. This is crucial for deduplication.
        """
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, content))

    def _normalize_keys(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converts dictionary keys to snake_case to match Database Schema expectations.
        Example: "Fiscal Year" -> "fiscal_year", "HW/SW" -> "hw_sw"
        """
        normalized = {}
        for k, v in data.items():
            if k is None: continue
            # Convert to lower case, replace spaces/slashes/dashes with underscores
            new_key = k.lower().strip().replace(" ", "_").replace("/", "_").replace("-", "_")
            # Remove any double underscores if they appear
            new_key = new_key.replace("__", "_")
            normalized[new_key] = v
        return normalized

    def format_page_content(self, data: dict) -> str:
        """
        Converts the raw data dictionary (snake_case keys) into a semantic string for embedding.
        """
        # Derive data type from source_sheet
        sheet = (data.get('source_sheet') or '').lower()
        if 'mm' in sheet and '$' not in sheet:
            data_label = "Man-Months"
            metric_label = f"TM1 MM: {data.get('tm1_mm', 0)}, ODS MM: {data.get('ods_mm', 0)}"
        else:
            data_label = "Spend ($M)"
            metric_label = f"TM1 ($M): {data.get('tm1_mm', 0)}, ODS ($M): {data.get('ods_mm', 0)}"

        lines = []
        lines.append(f"Data Type: {data_label}")
        lines.append(f"Project: {data.get('project_desc', 'N/A')} ({data.get('project_number', 'N/A')})")
        lines.append(f"Fiscal Year: {data.get('fiscal_year', 'N/A')} {data.get('fiscal_quarter', 'N/A')}")
        lines.append(f"Department: {data.get('home_dept_desc', 'N/A')} (Lead: {data.get('dept_lead', 'N/A')})")
        lines.append(f"Expense Type: {data.get('exp_type_r5', 'N/A')} - {data.get('exp_type_r3', 'N/A')}")
        lines.append(metric_label)
        lines.append(f"Details: HW/SW: {data.get('hw_sw', 'N/A')}, Location: {data.get('home_dept_region_r2', 'N/A')}")

        return "\n".join(lines)

    def process_jsonl(self, file_path: str):
        """Reads JSONL, creates Documents, and ingests them."""
        logger.info(f"Reading data from {file_path}...")
        
        documents = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_number, line in enumerate(f):
                    if not line.strip():
                        continue
                    
                    try:
                        record = json.loads(line)
                        
                        # Extract core data
                        source_meta = {
                            "source_file": record.get("source_file"),
                            "source_sheet": record.get("source_sheet")
                        }
                        
                        # Handle 'metadata' vs 'data' key (from previous issue)
                        raw_data = record.get("metadata") or record.get("data", {})
                        
                        # Normalize keys (Fiscal Year -> fiscal_year)
                        data_payload = self._normalize_keys(raw_data)
                        
                        # 1. Create Page Content (Text to be embedded)
                        page_content = self.format_page_content(data_payload)
                        
                        # 2. Create Metadata (Payload + Source info)
                        metadata = {**source_meta, **data_payload}
                        
                        # 3. Generate UUID
                        doc_uuid = self.generate_deterministic_uuid(page_content)
                        
                        # 4. Create Document Object
                        doc = Document(
                            page_content=page_content,
                            metadata=metadata,
                            id=doc_uuid
                        )
                        documents.append(doc)
                        
                    except json.JSONDecodeError:
                        logger.warning(f"Skipping invalid JSON on line {line_number}")

            if documents:
                logger.info(f"Prepared {len(documents)} documents. Starting ingestion...")
                self.vector_store.add_documents(documents)
            else:
                logger.warning("No valid documents found to ingest.")
                
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest JSONL data into Vector Store.")
    parser.add_argument("--file", default="out/output.jsonl", help="Path to input JSONL file")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    
    args = parser.parse_args()
    
    agent = DataIngestionAgent(config_path=args.config)
    agent.process_jsonl(args.file)