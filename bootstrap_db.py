#!/usr/bin/env python
"""
FIRA — Financial Intelligence & Resource Analytics — Bootstrap Database

One-time (or idempotent) entry point that:
  1. Creates the cnss_opex_db database if it doesn't exist
  2. Enables the pgvector extension
  3. Creates all application tables (opex_data_hybrid, bpafg_demand, priority_template)
  4. Validates existing schemas and reports any mismatches

Usage:
    python bootstrap_db.py                     # uses config/config.yaml
    python bootstrap_db.py --config path.yaml  # custom config path
"""

import argparse
import logging
import sys

from db.setup_all_tables import DatabaseBootstrap


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Bootstrap the FIRA database (create DB, extensions, tables, indexes)."
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to config.yaml (default: config/config.yaml)",
    )
    args = parser.parse_args()

    logging.info("--- Running Database Bootstrap ---")

    try:
        bootstrap = DatabaseBootstrap(config_path=args.config)
        success = bootstrap.run()
    except Exception as e:
        logging.error(f"Bootstrap failed: {e}")
        sys.exit(1)

    if not success:
        logging.warning("Bootstrap completed with schema warnings — review output above.")
        sys.exit(1)

    logging.info("Bootstrap complete.")


if __name__ == "__main__":
    main()
