"""
Data Management Page — Upload and ingest data for OpEx, Resource Planner, and Headcount.

Provides:
  - OpEx Excel upload → JSONL conversion → vector embedding ingestion
  - Resource Planner CSV upload → PostgreSQL ingestion (hybrid-ready)
  - Headcount CSV upload → PostgreSQL ingestion
  - Explicit upload confirmation with file details
  - Progress status and logging during ingestion
  - Re-ingest buttons for all data sets
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
            "Upload and manage data for **OpEx Analytics**, **Resource Planner**, "
            "and **Headcount** modules."
        )

        # ── Health / row-count overview ──────────────────────────────────
        self._render_table_status()

        st.markdown("---")

        # ── Three tabs: OpEx | Resource Planner | Headcount ──────────────
        tab_opex, tab_rp, tab_hc = st.tabs([
            "OpEx Data (Hybrid/Vector)",
            "Resource Planner Data",
            "Headcount Data",
        ])

        with tab_opex:
            self._render_opex_section()

        with tab_rp:
            self._render_resource_planner_section()

        with tab_hc:
            self._render_headcount_section()

    # =====================================================================
    # Table health
    # =====================================================================
    def _render_table_status(self):
        """Show row counts for every application table."""
        tables = [
            ("opex_data_hybrid", "OpEx Hybrid"),
            ("bpafg_demand", "BPAFG Demand"),
            ("priority_template", "Priority Template"),
            ("headcount_data", "Headcount"),
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
        st.subheader("OpEx Data (Hybrid / Vector)")
        st.markdown(
            "OpEx Excel files are converted to JSONL, embedded via QGenie, "
            "and stored in `opex_data_hybrid` with vector similarity support."
        )

        # Upload
        uploaded = st.file_uploader(
            "Select OpEx Excel File(s)",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key="opex_upload",
        )

        # Show uploaded file confirmation
        if uploaded:
            st.success(f"**{len(uploaded)} file(s) selected for upload:**")
            for f in uploaded:
                size_kb = f.size / 1024
                st.markdown(f"- `{f.name}` ({size_kb:.1f} KB)")

        st.markdown("")

        # Action buttons
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            ingest_uploaded = st.button(
                "Upload & Ingest Files",
                key="opex_ingest_uploaded",
                disabled=not uploaded,
                type="primary",
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
        with st.status("Uploading files...", expanded=True) as status:
            for f in uploaded_files:
                dest = os.path.join(opex_dir, f.name)
                with open(dest, "wb") as out:
                    out.write(f.read())
                saved_names.append(f.name)
                st.write(f"Saved `{f.name}` to `files/opex/`")

            status.update(label=f"{len(saved_names)} file(s) uploaded successfully!", state="complete")

        st.success(f"Uploaded {len(saved_names)} file(s): {', '.join(saved_names)}")

        # Run the full pipeline
        self._run_opex_pipeline(extra_files=saved_names)

    def _run_opex_pipeline(self, extra_files=None):
        """
        Run the OpEx pipeline: DB bootstrap → Excel→JSONL → vector ingestion.
        Uses the same logic as main.py / data_pipeline.py.
        """
        with st.status("Running OpEx ingestion pipeline...", expanded=True) as status:
            try:
                st.write("**Step 1/3** — Bootstrapping database...")
                from db.setup_all_tables import DatabaseBootstrap
                bootstrap = DatabaseBootstrap(config_path="config/config.yaml")
                bootstrap.run()
                st.write("Database ready.")

                # ── Step 2: Excel → JSONL
                st.write("**Step 2/3** — Converting Excel to JSONL...")
                from utils.parsers.excel_to_json import convert_excel_to_jsonl
                convert_excel_to_jsonl()
                st.write("JSONL conversion complete.")

                # ── Step 3: Vector ingestion
                st.write("**Step 3/3** — Embedding & ingesting vectors...")
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
                    st.write("No JSONL files found to ingest. Check Excel file names in config.yaml.")
                else:
                    for jp in files_to_ingest:
                        st.write(f"Ingesting `{jp.name}`...")
                        agent.process_jsonl(str(jp))
                        st.write(f"`{jp.name}` ingested.")

                status.update(label="OpEx pipeline completed successfully!", state="complete")
                st.cache_data.clear()

            except Exception as e:
                status.update(label="Pipeline failed!", state="error")
                st.error(f"Pipeline failed: {e}")
                logger.exception(e)

    # =====================================================================
    # Resource Planner section
    # =====================================================================
    def _render_resource_planner_section(self):
        st.subheader("Resource Planner Data")
        st.markdown(
            "Resource Planner CSVs are parsed and stored in PostgreSQL tables "
            "(`bpafg_demand`, `priority_template`) for SQL analytics and the Resource Planner visualization."
        )

        col1, col2 = st.columns(2)
        with col1:
            demand_file = st.file_uploader(
                "Select Demand CSV (BPAFG)",
                type=["csv", "xlsx"],
                key="dm_demand_upload",
            )
        with col2:
            priority_file = st.file_uploader(
                "Select Priority Template CSV",
                type=["csv", "xlsx"],
                key="dm_priority_upload",
            )

        # Show uploaded file confirmation
        if demand_file:
            size_kb = demand_file.size / 1024
            st.info(f"Demand file selected: `{demand_file.name}` ({size_kb:.1f} KB)")
        if priority_file:
            size_kb = priority_file.size / 1024
            st.info(f"Priority file selected: `{priority_file.name}` ({size_kb:.1f} KB)")

        st.markdown("")

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            ingest_btn = st.button(
                "Upload & Ingest Files",
                key="dm_rp_ingest",
                disabled=not (demand_file or priority_file),
                type="primary",
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

        with st.status("Ingesting resource planner data...", expanded=True) as status:
            try:
                if demand_file:
                    st.write(f"Saving `{demand_file.name}` to `files/resource/`...")
                    save_path = os.path.join(resource_dir, demand_file.name)
                    with open(save_path, "wb") as f:
                        f.write(demand_file.read())
                    demand_file.seek(0)
                    st.write(f"File uploaded. Parsing demand data...")
                    df = parse_bpafg_demand(save_path)
                    n = insert_bpafg_to_db(df, cur, use_postgres=True)
                    st.write(f"Ingested **{n}** demand rows.")

                if priority_file:
                    st.write(f"Saving `{priority_file.name}` to `files/resource/`...")
                    save_path = os.path.join(resource_dir, priority_file.name)
                    with open(save_path, "wb") as f:
                        f.write(priority_file.read())
                    priority_file.seek(0)
                    st.write(f"File uploaded. Parsing priority data...")
                    df = parse_priority_template(save_path)
                    n = insert_priority_to_db(df, cur, use_postgres=True)
                    st.write(f"Ingested **{n}** priority rows.")

                conn.commit()
                st.cache_data.clear()
                status.update(label="Resource planner data ingested successfully!", state="complete")

            except Exception as e:
                conn.rollback()
                status.update(label="Ingestion failed!", state="error")
                st.error(f"Ingest error: {e}")
                logger.exception(e)
            finally:
                conn.close()

    def _run_rp_reingest(self):
        """Re-ingest all files from ../files/resource/."""
        with st.status("Re-ingesting resource planner data from files/resource/...", expanded=True) as status:
            try:
                from utils.parsers.cbn_data_parser import ingest_all
                from db.cbn_tables import setup_tables_postgres, get_pg_connection

                resource_dir = os.path.join("..", "files", "resource")
                os.makedirs(resource_dir, exist_ok=True)
                st.write("Setting up tables...")
                setup_tables_postgres()

                conn = get_pg_connection()
                try:
                    st.write("Parsing and ingesting files...")
                    n = ingest_all(resource_dir, conn.cursor(), use_postgres=True)
                    conn.commit()
                    st.write(f"Ingested **{n}** total rows.")
                    st.cache_data.clear()
                    status.update(label=f"Re-ingested {n} rows from files/resource/", state="complete")
                finally:
                    conn.close()
            except Exception as e:
                status.update(label="Re-ingestion failed!", state="error")
                st.error(f"Re-ingest error: {e}")
                logger.exception(e)

    # =====================================================================
    # Headcount section
    # =====================================================================
    def _render_headcount_section(self):
        st.subheader("Headcount Data")
        st.markdown(
            "Upload headcount data files (CSV/XLSX) for workforce analytics. "
            "Data is stored in the `headcount_data` table in PostgreSQL."
        )

        uploaded = st.file_uploader(
            "Select Headcount CSV/XLSX File(s)",
            type=["csv", "xlsx", "xls"],
            accept_multiple_files=True,
            key="hc_upload",
        )

        # Show uploaded file confirmation
        if uploaded:
            st.success(f"**{len(uploaded)} file(s) selected for upload:**")
            for f in uploaded:
                size_kb = f.size / 1024
                st.markdown(f"- `{f.name}` ({size_kb:.1f} KB)")

        st.markdown("")

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            ingest_btn = st.button(
                "Upload & Ingest Files",
                key="hc_ingest",
                disabled=not uploaded,
                type="primary",
            )
        with btn_col2:
            reingest_btn = st.button(
                "Re-ingest from files/headcount",
                key="hc_reingest",
            )

        if ingest_btn and uploaded:
            self._ingest_headcount_uploaded(uploaded)

        if reingest_btn:
            self._run_headcount_reingest()

    def _ingest_headcount_uploaded(self, uploaded_files):
        """Save and ingest headcount CSV/XLSX files."""
        import pandas as pd

        hc_dir = os.path.join("..", "files", "headcount")
        os.makedirs(hc_dir, exist_ok=True)

        with st.status("Ingesting headcount data...", expanded=True) as status:
            try:
                total_rows = 0
                for f in uploaded_files:
                    # Save file
                    save_path = os.path.join(hc_dir, f.name)
                    with open(save_path, "wb") as out:
                        out.write(f.read())
                    f.seek(0)
                    st.write(f"Uploaded `{f.name}` to `files/headcount/`")

                    # Parse
                    if f.name.endswith(".csv"):
                        df = pd.read_csv(f)
                    else:
                        df = pd.read_excel(f)

                    st.write(f"Parsed {len(df)} rows, {len(df.columns)} columns from `{f.name}`")

                    # Ingest to PostgreSQL
                    n = self._insert_headcount_to_db(df)
                    total_rows += n
                    st.write(f"Ingested **{n}** rows from `{f.name}`")

                st.cache_data.clear()
                status.update(label=f"Headcount: {total_rows} total rows ingested!", state="complete")

            except Exception as e:
                status.update(label="Headcount ingestion failed!", state="error")
                st.error(f"Headcount ingest error: {e}")
                logger.exception(e)

    def _run_headcount_reingest(self):
        """Re-ingest all headcount files from ../files/headcount/."""
        import pandas as pd

        hc_dir = os.path.join("..", "files", "headcount")
        if not os.path.exists(hc_dir):
            st.warning("No `files/headcount/` directory found. Upload files first.")
            return

        with st.status("Re-ingesting headcount data from files/headcount/...", expanded=True) as status:
            try:
                total_rows = 0
                files = [f for f in os.listdir(hc_dir) if f.endswith((".csv", ".xlsx", ".xls"))]
                if not files:
                    st.warning("No CSV/XLSX files found in files/headcount/")
                    status.update(label="No files found", state="error")
                    return

                for fname in files:
                    fpath = os.path.join(hc_dir, fname)
                    st.write(f"Processing `{fname}`...")
                    if fname.endswith(".csv"):
                        df = pd.read_csv(fpath)
                    else:
                        df = pd.read_excel(fpath)
                    n = self._insert_headcount_to_db(df)
                    total_rows += n
                    st.write(f"Ingested **{n}** rows from `{fname}`")

                st.cache_data.clear()
                status.update(label=f"Re-ingested {total_rows} headcount rows", state="complete")

            except Exception as e:
                status.update(label="Re-ingestion failed!", state="error")
                st.error(f"Headcount re-ingest error: {e}")
                logger.exception(e)

    @staticmethod
    def _insert_headcount_to_db(df) -> int:
        """Insert a headcount DataFrame into the headcount_data table.
        Creates the table dynamically based on the DataFrame columns."""
        from sqlalchemy import text
        from utils.models.database import OpexDB

        # Normalize column names
        df.columns = [c.strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns]

        with OpexDB.engine.begin() as conn:
            # Create table if not exists — dynamic schema from DataFrame
            cols_sql = []
            for col in df.columns:
                if df[col].dtype in ("int64", "int32"):
                    cols_sql.append(f'"{col}" INTEGER')
                elif df[col].dtype in ("float64", "float32"):
                    cols_sql.append(f'"{col}" DOUBLE PRECISION')
                else:
                    cols_sql.append(f'"{col}" TEXT')

            create_sql = f"""
                CREATE TABLE IF NOT EXISTS headcount_data (
                    id SERIAL PRIMARY KEY,
                    {', '.join(cols_sql)}
                )
            """
            conn.execute(text(create_sql))

            # Insert rows
            if not df.empty:
                col_names = ', '.join([f'"{c}"' for c in df.columns])
                placeholders = ', '.join([f':{c}' for c in df.columns])
                insert_sql = f"INSERT INTO headcount_data ({col_names}) VALUES ({placeholders})"
                records = df.to_dict(orient="records")
                conn.execute(text(insert_sql), records)

        return len(df)

    # =====================================================================
    # Shared helpers
    # =====================================================================
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
