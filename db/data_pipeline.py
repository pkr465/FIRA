import time
import os
import logging
from pathlib import Path

# --- Imports from our application modules ---
from config.config import Config  # Updated to use the Config object
from utils.parsers.excel_to_json import convert_excel_to_jsonl
from db.setup_all_tables import DatabaseBootstrap
from agents.data_ingestion_agent import DataIngestionAgent

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def run_pipeline(config_path="config/config.yaml", sheet_name=None):
    """
    Executes the data pipeline: DB setup, Excel conversion, and Vector ingestion.
    """
    logger.info("==========================================")
    logger.info("   🚀 STARTING QGENIE DATA PIPELINE      ")
    logger.info("==========================================")
    start_time = time.time()

    # --- 1. Validation ---
    # Ensure Config is loaded (it loads on import, but we check critical paths)
    if not Config.SOURCE_PATH or not Config.OUT_PATH:
        logger.error("❌ Configuration invalid: SOURCE_PATH or OUT_PATH missing.")
        return

    # --- 2. Initialize Database Schema ---
    logger.info("\n--- Step 1: Initializing Database Schema ---")
    try:
        bootstrap = DatabaseBootstrap(config_path=config_path)
        bootstrap.run()
        logger.info("✅ Database schema verified.")
        
    except Exception as e:
        logger.error(f"❌ Halting: Database setup failed: {e}", exc_info=True)
        return

    # --- 3. Execute Excel to JSONL Conversion ---
    logger.info("\n--- Step 2: Excel to JSONL Conversion ---")
    
    try:
        if sheet_name:
            logger.info(f"Targeting specific sheet: {sheet_name}")

        convert_excel_to_jsonl(sheet_name_to_process=sheet_name)
        logger.info("✅ Conversion phase completed.")

    except Exception as e:
        logger.error(f"❌ Halting: Excel conversion failed: {e}", exc_info=True)
        return

    # --- 4. Execute Vector Ingestion ---
    logger.info("\n--- Step 3: Vector Ingestion (Hybrid Table) ---")
    try:
        # Initialize the agent
        logger.info("Initializing Data Ingestion Agent...")
        agent = DataIngestionAgent(config_path=config_path)
        
        # Calculate expected JSONL files based on Config
        # Logic matches excel_to_json.py: output_<stem>.jsonl
        files_to_ingest = []
        if Config.EXCEL_FILE_NAMES:
            for fname in Config.EXCEL_FILE_NAMES:
                fname = fname.strip()
                if not fname: continue
                
                stem = Path(fname).stem
                jsonl_path = Config.OUT_PATH / f"output_{stem}.jsonl"
                files_to_ingest.append(jsonl_path)
        
        if not files_to_ingest:
            logger.warning("⚠️ No Excel files defined in Config to ingest.")
            return

        # Iterate and Ingest
        success_count = 0
        for jsonl_path in files_to_ingest:
            if not jsonl_path.exists():
                logger.error(f"❌ JSONL file not found: {jsonl_path} (Conversion might have failed)")
                continue
                
            logger.info(f"📥 Ingesting: {jsonl_path.name}")
            try:
                agent.process_jsonl(str(jsonl_path))
                success_count += 1
            except Exception as e:
                logger.error(f"❌ Failed to ingest {jsonl_path.name}: {e}")

        if success_count > 0:
            logger.info(f"✅ Ingestion completed for {success_count}/{len(files_to_ingest)} files.")
        else:
            logger.error("❌ No files were successfully ingested.")

    except Exception as e:
        logger.error(f"❌ Halting: Vector ingestion failed: {e}", exc_info=True)
        return

    # --- 5. Report Total Time Taken ---
    end_time = time.time()
    duration = end_time - start_time
    logger.info("\n==========================================")
    logger.info(f"🎉 Pipeline Finished. Total time: {duration:.2f}s")
    logger.info("==========================================")

if __name__ == "__main__":
    # Ensure this matches your actual config location
    run_pipeline("config/config.yaml")