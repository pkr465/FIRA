import pandas as pd
import json
import os
import argparse
import numpy as np
import hashlib
import logging
from pathlib import Path

# Import the Config object from the file we just updated
try:
    from config.config import Config
except ImportError:
    # Fallback/Error if config.py isn't found
    Config = None

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def generate_uuid(content: dict) -> str:
    """Generate a deterministic UUID based on record content."""
    content_str = json.dumps(content, sort_keys=True, default=str)
    return hashlib.sha256(content_str.encode("utf-8")).hexdigest()

def convert_excel_to_jsonl(sheet_name_to_process=None):
    """
    Converts Excel file(s) defined in Config to JSONL files.
    Skips if output file already exists.
    """
    if not Config:
        logger.error("Could not import Config from config.py. Ensure the file exists.")
        return

    # --- 1. Resolve Directories ---
    source_dir = Config.SOURCE_PATH
    out_dir = Config.OUT_PATH

    if not source_dir:
        logger.error("Source path (SOURCE_PATH) not defined in Config.")
        return
        
    if not out_dir:
        # Fallback to current directory if not set
        out_dir = Path(".")

    # Ensure output directory exists
    os.makedirs(out_dir, exist_ok=True)

    # --- 2. Get File List ---
    files_to_process = Config.EXCEL_FILE_NAMES

    if not files_to_process:
        logger.error("No Excel files found in Config.EXCEL_FILE_NAMES.")
        return

    logger.info(f"Found {len(files_to_process)} file(s) in config to process.")

    # --- 3. Process Each File ---
    for file_name in files_to_process:
        file_name = file_name.strip()
        if not file_name: continue

        input_path = source_dir / file_name
        
        # Construct output filename: output_<original_name_without_extension>.jsonl
        stem = Path(file_name).stem
        output_filename = f"output_{stem}.jsonl"
        output_path = out_dir / output_filename

        # Check if exists
        if output_path.exists():
            logger.info(f"⏭️  Skipping {file_name} (Output already exists: {output_path})")
            continue

        if not input_path.exists():
            logger.warning(f"⚠️  Input file not found: {input_path}")
            continue

        logger.info(f"📂 Processing: {input_path} -> {output_path}")
        
        try:
            xls = pd.ExcelFile(input_path)
            sheets = [sheet_name_to_process] if sheet_name_to_process else xls.sheet_names
            
            record_count = 0
            
            with open(output_path, 'w', encoding='utf-8') as f_out:
                for sheet in sheets:
                    if sheet not in xls.sheet_names:
                        logger.warning(f"   Sheet '{sheet}' not found in {file_name}")
                        continue
                    
                    try:
                        df = pd.read_excel(xls, sheet_name=sheet)
                        # Replace NaN with None for valid JSON
                        df = df.replace({np.nan: None})
                        
                        records = df.to_dict(orient='records')
                        logger.info(f"   -> Sheet '{sheet}': {len(records)} records")
                        
                        for row_data in records:
                            row_uuid = generate_uuid(row_data)
                            
                            entry = {
                                "uuid": row_uuid,
                                "source_file": file_name,
                                "source_sheet": sheet,
                                "metadata": row_data,
                                "page_content": json.dumps(row_data, default=str)
                            }
                            
                            f_out.write(json.dumps(entry) + '\n')
                            record_count += 1
                            
                    except Exception as e:
                        logger.error(f"   Error reading sheet '{sheet}': {e}")

            logger.info(f"✅ Generated {output_path} ({record_count} records)")

        except Exception as e:
            logger.error(f"❌ Failed to process {file_name}: {e}", exc_info=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--sheet', default=None, help="Specific sheet to process")
    args = parser.parse_args()
    
    convert_excel_to_jsonl(args.sheet)