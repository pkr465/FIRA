import logging
import uuid
import json
from typing import List, Set
from sqlalchemy import create_engine, text
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from config.schema_config import SCHEMA_CONFIG

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PostgresVectorStore:
    def __init__(
        self,
        connection_string: str,
        embedding_function: Embeddings,
        hybrid_table_name: str = "opex_data_hybrid"
    ):
        """
        Initializes the Vector Store.
        Writes DIRECTLY to the single hybrid table (Metadata + Vector).
        """
        self.connection_string = connection_string
        self.embedding_function = embedding_function
        
        # Load table name from config or use default
        self.table_name = SCHEMA_CONFIG.get("table_name", hybrid_table_name)
        self.vector_col = SCHEMA_CONFIG.get("vector_config", {}).get("column_name", "vector")
        
        self.engine = create_engine(connection_string)
        self._verify_vector_extension()

    def _verify_vector_extension(self):
        try:
            with self.engine.connect() as conn:
                # Check for extension
                result = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
                if not result.fetchone():
                    logger.warning("⚠️  'vector' extension not detected. Attempting to create...")
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                    conn.commit()
        except Exception as e:
            logger.warning(f"⚠️  Extension verification check failed (might be permissions): {e}")

    def _fetch_existing_uuids(self, ids: List[str]) -> Set[str]:
        """
        Checks the hybrid table for existing UUIDs to prevent duplicates.
        """
        if not ids:
            return set()
        
        existing_ids = set()
        try:
            with self.engine.connect() as conn:
                placeholders = ', '.join([f":id_{i}" for i in range(len(ids))])
                params = {f"id_{i}": uid for i, uid in enumerate(ids)}

                query = text(f"""
                    SELECT uuid FROM {self.table_name}
                    WHERE uuid IN ({placeholders})
                """)
                
                result = conn.execute(query, params)
                existing_ids = {str(row[0]) for row in result}
                
        except Exception as e:
            logger.debug(f"Could not pre-fetch existing UUIDs: {e}")
            return set()

        return existing_ids

    def add_documents(self, documents: List[Document], batch_size: int = 500, force: bool = False):
        if not documents:
            return

        # 1. Deduplicate Input (within the incoming list)
        unique_docs_map = {}
        for doc in documents:
            doc_id = doc.metadata.get("id")
            if not doc_id:
                # Generate deterministic UUID based on content if missing
                doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, doc.page_content))
                doc.metadata["id"] = doc_id
            unique_docs_map[doc_id] = doc

        deduped_docs = list(unique_docs_map.values())

        if force:
            # Force mode: skip DB dedup check, let UPSERT handle everything.
            # Used when schema changes require re-ingesting existing data.
            new_docs = deduped_docs
            logger.info(f"🔄 Force mode: re-ingesting all {len(new_docs)} documents (UPSERT will update existing)...")
        else:
            # 2. Database Deduplication (Check Hybrid Table)
            all_ids = list(unique_docs_map.keys())
            existing_ids = set()

            chk_size = 1000
            for i in range(0, len(all_ids), chk_size):
                id_chunk = all_ids[i : i + chk_size]
                existing_ids.update(self._fetch_existing_uuids(id_chunk))

            new_docs = [doc for doc in deduped_docs if doc.metadata["id"] not in existing_ids]

            if not new_docs:
                logger.info("✅ All documents already exist. Skipping. (Use force=True to re-ingest)")
                return

        logger.info(f"🚀 Ingesting {len(new_docs)} new documents into '{self.table_name}'...")

        # 3. Batch Insert
        total_docs = len(new_docs)
        total_batches = (total_docs + batch_size - 1) // batch_size

        for i in range(0, total_docs, batch_size):
            batch = new_docs[i : i + batch_size]
            batch_texts = [d.page_content for d in batch]
            
            current_batch_num = (i // batch_size) + 1
            logger.info(f"   Processing batch {current_batch_num}/{total_batches} ({len(batch)} docs)...")

            try:
                # A. Generate Embeddings
                embeddings = self.embedding_function.embed_documents(batch_texts)
                
                # B. Prepare Records
                records = []
                for j, doc in enumerate(batch):
                    meta = doc.metadata
                    
                    def clean_num(val): return val if val not in [None, ""] else None

                    # Derive data_type from source_sheet name
                    sheet = (meta.get("source_sheet") or "").lower()
                    if "mm" in sheet and "$" not in sheet:
                        data_type = "mm"
                    elif "$" in sheet or "dollar" in sheet:
                        data_type = "dollar"
                    else:
                        data_type = "dollar"  # default

                    record = {
                        "uuid": meta.get("id"),
                        "source_file": meta.get("source_file"),
                        "source_sheet": meta.get("source_sheet"),
                        "data_type": data_type,
                        "fiscal_year": clean_num(meta.get("fiscal_year")),
                        "project_number": clean_num(meta.get("project_number")),
                        "dept_lead": meta.get("dept_lead"),
                        "hw_sw": meta.get("hw_sw"),
                        # Dollar columns — from $Data sheet
                        "tm1_m":  clean_num(meta.get("tm1_m")),
                        "ods_m":  clean_num(meta.get("ods_m")),
                        # Man-month columns — from MM Data sheet
                        "tm1_mm": clean_num(meta.get("tm1_mm")),
                        "ods_mm": clean_num(meta.get("ods_mm")),
                        "additional_data": json.dumps(meta),
                        "vector": embeddings[j]
                    }
                    records.append(record)

                # C. Insert
                with self.engine.begin() as conn:
                    stmt = text(f"""
                        INSERT INTO {self.table_name} (
                            uuid, source_file, source_sheet, data_type,
                            fiscal_year, project_number, dept_lead, hw_sw,
                            tm1_m, ods_m, tm1_mm, ods_mm,
                            additional_data, {self.vector_col}
                        )
                        VALUES (
                            :uuid, :source_file, :source_sheet, :data_type,
                            :fiscal_year, :project_number, :dept_lead, :hw_sw,
                            :tm1_m, :ods_m, :tm1_mm, :ods_mm,
                            :additional_data, :vector
                        )
                        ON CONFLICT (uuid) DO UPDATE SET
                            data_type = EXCLUDED.data_type,
                            fiscal_year = EXCLUDED.fiscal_year,
                            project_number = EXCLUDED.project_number,
                            dept_lead = EXCLUDED.dept_lead,
                            hw_sw = EXCLUDED.hw_sw,
                            tm1_m = EXCLUDED.tm1_m,
                            ods_m = EXCLUDED.ods_m,
                            tm1_mm = EXCLUDED.tm1_mm,
                            ods_mm = EXCLUDED.ods_mm,
                            additional_data = EXCLUDED.additional_data,
                            {self.vector_col} = EXCLUDED.{self.vector_col},
                            updated_at = NOW();
                    """)
                    conn.execute(stmt, records)

            except Exception as e:
                logger.error(f"❌ Error ingesting batch {current_batch_num}: {e}")
                raise e
        
        logger.info("🎉 Ingestion complete.")