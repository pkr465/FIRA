import argparse
import logging
from db.data_pipeline import run_pipeline

# Configure logging for consistent output format
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    """
    Main function to parse arguments and trigger the data pipeline.
    """
    # --- 1. Argument Parsing ---
    parser = argparse.ArgumentParser(description='Setup DB, Convert Excel, and Ingest Embeddings.')
    parser.add_argument(
        '--config',
        type=str,
        default="config/config.yaml",
        help='Path to the configuration YAML file.'
    )
    parser.add_argument(
        '--sheet',
        type=str,
        default=None,
        help='Optional: Process only a specific sheet name during Excel conversion.'
    )
    args = parser.parse_args()

    # Execute the pipeline logic defined in data_pipeline.py
    run_pipeline(config_path=args.config, sheet_name=args.sheet)

if __name__ == '__main__':
    main()