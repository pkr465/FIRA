"""
Data Management Page — Upload and ingest data for both OpEx and Resource Planner.

Provides:
  - OpEx Excel upload → JSONL conversion → vector embedding ingestion
  - Resource Planner CSV upload → PostgreSQL ingestion
  - Re-ingest buttons for both data sets
  - Table row counts & health status
"""

import os
import logging
import time
import streamlit as st
from pathlib import Path

from .base import PageBase
from config.config import Config

logger = logging.getLogger(__name__)


class DataManagement(PageBase):
    """Unified data upload and ingestion page."""

    def render(self):
        super().render()

        st.markdown(
            "Upload and manage data for both the **OpEx Analytics** modules "
            "and the **FIRA Resource Planner**."
        )

        # ── Health / row-count overview ──────────────────────────────────
        self._render_table_status()

        st.markdown("---")

        # ── Two-column layout: OpEx | Resource Planner ──────────────────
        col_opex, col_rp = st.columns(2)

        with col_opex:
            st.subheader("OpEx Data (Vector/Hybrid)")
            self._render_opex_section()

        with col_rp:
            st.subheader("Resource Planner (Relational)")
            self._render_resource_planner_section()

    # =====================================================================
    # Table health
    # =====================================================================
    def _render_table_status(self):
        """Show row counts for every application table."""
        tables = [
            ("opex_data_hybrid", "OpEx Hybrid"),
            ("bpafg_demand", "BPAFG Demand"),
            ("priority_template", "Priority Template"),
        ]

        cols = st.columns(len(tables))
        for col, (tbl, label) in zip(cols, tables):
            count = self._table_row_count(tbl)
            with col:
                if count is None:
                    st.metric(label, "—", help=f"Table '{tbl}' not found or DB unavailable")
                else:
                    st.metric(label, f"{count:,} rows")

    @staticmethod
    @st.cache_data(ttl=30)
    def _table_row_count(table_name: str):
        """Return row count or None if the table doesn't exist."""
        try:
            from utils.models.database import OpexDB
            from sqlalchemy import text
            with OpexDB.engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                return result.scalar()
        except Exception:
            return None

    # =====================================================================
    # OpEx section
    # =====================================================================
    def _render_opex_section(self):
        st.markdown(
            "OpEx Excel files are converted to JSONL, embedded via QGenie, "
            "and stored in `opex_data_hybrid` with vector similarity support."
        )

        # Upload
        uploaded = st.file_uploader(
            "Upload OpEx Excel File(s)",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key="opex_upload",
        )

        # Action buttons
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            ingest_uploaded = st.button(
                "Ingest Uploaded Files",
                key="opex_ingest_uploaded",
                disabled=not uploaded,
            )
        with btn_col2:
            reingest = st.button(
                "Re-ingest from files/opex",
                key="opex_reingest",
            )

        if ingest_uploaded and uploaded:
            self._ingest_opex_uploaded(uploaded)

        if reingest:
            self._run_opex_pipeline()

    def _ingest_opex_uploaded(self, uploaded_files):
        """Save uploaded Excel files to ../files/opex/ then run the full pipeline."""
        opex_dir = os.path.join("..", "files", "opex")
        os.makedirs(opex_dir, exist_ok=True)

        saved_names = []
        for f in uploaded_files:
            dest = os.path.join(opex_dir, f.name)
            with open(dest, "wb") as out:
                out.write(f.read())
            saved_names.append(f.name)

        st.info(f"Saved {len(saved_names)} file(s) to `files/opex/`: {', '.join(saved_names)}")

        # Update config Excel file names to include uploaded files
        # so that data_pipeline picks them up
        self._run_opex_pipeline(extra_files=saved_names)

    def _run_opex_pipeline(self, extra_files=None):
        """
        Run the OpEx pipeline: DB bootstrap → Excel→JSONL → vector ingestion.
        Uses the same logic as main.py / data_pipeline.py.
        """
        progress = st.empty()
        log_area = st.empty()
        logs = []

        def _log(msg):
            logs.append(msg)
            log_area.code("\n".join(logs[-20:]), language="text")

        try:
            progress.progress(0, text="Step 1/3 — Bootstrapping database...")
            _log("Bootstrapping database tables...")

            from db.setup_all_tables import DatabaseBootstrap
            bootstrap = DatabaseBootstrap(config_path="config/config.yaml")
            bootstrap.run()
            _log("  ✅ Database ready.")

            # ── Step 2: Excel → JSONL ────────────────────────────────────
            progress.progress(33, text="Step 2/3 — Converting Excel to JSONL...")
            _log("Converting Excel files to JSONL...")

            from utils.parsers.excel_to_json import convert_excel_to_jsonl
            convert_excel_to_jsonl()
            _log("  ✅ JSONL conversion complete.")

            # ── Step 3: Vector ingestion ─────────────────────────────────
            progress.progress(66, text="Step 3/3 — Embedding & ingesting vectors...")
            _log("Starting vector embedding ingestion...")

            from agents.data_ingestion_agent import DataIngestionAgent
            agent = DataIngestionAgent(config_path="config/config.yaml")

            files_to_ingest = []
            file_names = list(Config.EXCEL_FILE_NAMES or [])
            if extra_files:
                file_names.extend(extra_files)
            # deduplicate
            seen = set()
            for fname in file_names:
                fname = fname.strip()
                if fname and fname not in seen:
                    seen.add(fname)
                    stem = Path(fname).stem
                    jsonl_path = Path(Config.OUT_PATH) / f"output_{stem}.jsonl"
                    if jsonl_path.exists():
                        files_to_ingest.append(jsonl_path)

            if not files_to_ingest:
                _log("  ⚠️ No JSONL files found to ingest. Check Excel file names in config.yaml.")
            else:
                for jp in files_to_ingest:
                    _log(f"  Ingesting {jp.name} ...")
                    agent.process_jsonl(str(jp))
                    _log(f"  ✅ {jp.name} done.")

            progress.progress(100, text="Pipeline complete!")
            st.success("OpEx data pipeline completed successfully.")
            st.cache_data.clear()

        except Exception as e:
            _log(f"  ❌ Error: {e}")
            st.error(f"Pipeline failed: {e}")
            logger.exception(e)

    # =====================================================================
    # Resource Planner section
    # =====================================================================
    def _render_resource_planner_section(self):
        st.markdown(
            "Resource Planner CSVs are parsed and stored in relational tables "
            "(`bpafg_demand`, `priority_template`) for SQL analytics."
        )

        col1, col2 = st.columns(2)
        with col1:
            demand_file = st.file_uploader(
                "Upload Demand CSV (BPAFG)",
                type=["csv", "xlsx"],
                key="dm_demand_upload",
            )
        with col2:
            priority_file = st.file_uploader(
                "Upload Priority Template CSV",
                type=["csv", "xlsx"],
                key="dm_priority_upload",
            )

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            ingest_btn = st.button(
                "Ingest Uploaded Files",
                key="dm_rp_ingest",
                disabled=not (demand_file or priority_file),
            )
        with btn_col2:
            reingest_btn = st.button(
                "Re-ingest from files/resource",
                key="dm_rp_reingest",
            )

        if ingest_btn:
            self._ingest_rp_uploaded(demand_file, priority_file)

        if reingest_btn:
            self._run_rp_reingest()

    def _ingest_rp_uploaded(self, demand_file, priority_file):
        """Parse and ingest uploaded resource planner files."""
        from utils.parsers.cbn_data_parser import (
            parse_bpafg_demand, parse_priority_template,
            insert_bpafg_to_db, insert_priority_to_db,
        )

        resource_dir = os.path.join("..", "files", "resource")
        os.makedirs(resource_dir, exist_ok=True)

        conn = self._get_pg_connection()
        if conn is None:
            return
        cur = conn.cursor()

        try:
            if demand_file:
                save_path = os.path.join(resource_dir, demand_file.name)
                with open(save_path, "wb") as f:
                    f.write(demand_file.read())
                demand_file.seek(0)
                df = parse_bpafg_demand(save_path)
                n = insert_bpafg_to_db(df, cur, use_postgres=True)
                st.success(f"Ingested {n} demand rows.")

            if priority_file:
                save_path = os.path.join(resource_dir, priority_file.name)
                with open(save_path, "wb") as f:
                    f.write(priority_file.read())
                priority_file.seek(0)
                df = parse_priority_template(save_path)
                n = insert_priority_to_db(df, cur, use_postgres=True)
                st.success(f"Ingested {n} priority rows.")

            conn.commit()
            st.cache_data.clear()

        except Exception as e:
            conn.rollback()
            st.error(f"Ingest error: {e}")
            logger.exception(e)
        finally:
            conn.close()

    def _run_rp_reingest(self):
        """Re-ingest all files from ../files/resource/."""
        try:
            from utils.parsers.cbn_data_parser import ingest_all
            from db.cbn_tables import setup_tables_postgres, get_pg_connection

            resource_dir = os.path.join("..", "files", "resource")
            os.makedirs(resource_dir, exist_ok=True)
            setup_tables_postgres()

            conn = get_pg_connection()
            try:
                n = ingest_all(resource_dir, conn.cursor(), use_postgres=True)
                conn.commit()
                st.success(f"Ingested {n} total rows from files/resource/.")
                st.cache_data.clear()
            finally:
                conn.close()
        except Exception as e:
            st.error(f"Re-ingest error: {e}")
            logger.exception(e)

    @staticmethod
    def _get_pg_connection():
        """Get a psycopg2 connection, creating tables if needed."""
        try:
            from db.cbn_tables import setup_tables_postgres, get_pg_connection
            setup_tables_postgres()
            return get_pg_connection()
        except Exception as e:
            st.error(f"Cannot connect to PostgreSQL: {e}")
            return None
