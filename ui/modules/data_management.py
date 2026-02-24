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

        # ── Delete Data ───────────────────────────────────────────────────
        self._render_delete_section()

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
    # Delete Data
    # =====================================================================
    def _render_delete_section(self):
        """Render delete-data controls with confirmation."""
        with st.expander("Delete Data", expanded=False):
            st.caption(
                "Truncate (empty) tables while keeping the schema intact. "
                "Subsequent ingestion will work normally."
            )

            TABLE_MAP = {
                "opex_data_hybrid": "OpEx Hybrid",
                "bpafg_demand": "BPAFG Demand",
                "priority_template": "Priority Template",
                "headcount_data": "Headcount",
                "langchain_pg_embedding": "LangChain Embeddings",
                "langchain_pg_collection": "LangChain Collections",
            }

            cols = st.columns(len(TABLE_MAP) + 1)

            # Per-table delete buttons
            for i, (tbl, label) in enumerate(TABLE_MAP.items()):
                with cols[i]:
                    if st.button(f"Delete {label}", key=f"del_{tbl}"):
                        st.session_state[f"confirm_del_{tbl}"] = True

                    if st.session_state.get(f"confirm_del_{tbl}"):
                        st.warning(f"Delete all **{label}** data?")
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("Confirm", key=f"confirm_yes_{tbl}", type="primary"):
                                self._truncate_tables([tbl])
                                st.session_state[f"confirm_del_{tbl}"] = False
                                st.cache_data.clear()
                                st.rerun()
                        with c2:
                            if st.button("Cancel", key=f"confirm_no_{tbl}"):
                                st.session_state[f"confirm_del_{tbl}"] = False
                                st.rerun()

            # Delete ALL button
            with cols[-1]:
                if st.button("Delete ALL Data", key="del_all", type="primary"):
                    st.session_state["confirm_del_all"] = True

                if st.session_state.get("confirm_del_all"):
                    st.error("This will delete **ALL** data from every table!")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Yes, Delete All", key="confirm_yes_all", type="primary"):
                            self._truncate_tables(list(TABLE_MAP.keys()))
                            st.session_state["confirm_del_all"] = False
                            st.cache_data.clear()
                            st.rerun()
                    with c2:
                        if st.button("Cancel", key="confirm_no_all"):
                            st.session_state["confirm_del_all"] = False
                            st.rerun()

    @staticmethod
    def _truncate_tables(table_names: list):
        """Truncate the given tables, resetting identity columns."""
        from sqlalchemy import text
        from utils.models.database import OpexDB

        try:
            with OpexDB.engine.begin() as conn:
                for tbl in table_names:
                    conn.execute(text(
                        f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE"
                    ))
            st.success(f"Deleted data from: {', '.join(table_names)}")
        except Exception as e:
            st.error(f"Delete failed: {e}")

    # =====================================================================
    # OpEx section
    # =====================================================================
    def _render_opex_section(self):
        st.subheader("OpEx Data (Hybrid / Vector)")
        st.markdown(
            "OpEx Excel files are converted to JSONL, embedded via QGenie, "
            "and stored in `opex_data_hybrid` with vector similarity support."
        )
        st.info(
            "**Note:** Re-uploading the same file is safe — duplicate records are "
            "automatically detected by content hash and skipped. Only new or changed "
            "records are added.",
            icon="ℹ️",
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
            self._run_opex_pipeline(force=True)

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

    def _run_opex_pipeline(self, extra_files=None, force: bool = False):
        """
        Run the OpEx pipeline: DB bootstrap → Excel→JSONL → vector ingestion.
        Uses the same logic as main.py / data_pipeline.py.

        Args:
            extra_files: Additional Excel file names to process.
            force: If True, re-ingest all records even if they already exist
                   (UPSERT updates existing rows with corrected column values).
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
                        mode = "force re-ingesting" if force else "ingesting"
                        st.write(f"{'🔄' if force else '📥'} {mode.capitalize()} `{jp.name}`...")
                        agent.process_jsonl(str(jp), force=force)
                        st.write(f"`{jp.name}` ingested.")

                status.update(label="OpEx pipeline completed successfully!", state="complete")
                st.cache_data.clear()
                # Count rows for celebration
                opex_count = self._table_row_count("opex_data_hybrid") or 0

            except Exception as e:
                opex_count = None
                status.update(label="Pipeline failed!", state="error")
                st.error(f"Pipeline failed: {e}")
                logger.exception(e)

        if opex_count is not None:
            self._celebrate_ingestion(opex_count, "OpEx")

    # =====================================================================
    # Resource Planner section
    # =====================================================================
    def _render_resource_planner_section(self):
        st.subheader("Resource Planner Data")
        st.markdown(
            "Resource Planner CSVs are parsed and stored in PostgreSQL tables "
            "(`bpafg_demand`, `priority_template`) for SQL analytics and the Resource Planner visualization."
        )
        st.info(
            "**Note:** Uploading new files **replaces** existing data in each table "
            "(demand or priority). This prevents duplicate rows when re-uploading "
            "updated files. The file on disk is also overwritten if it has the same name.",
            icon="ℹ️",
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
        """Parse and ingest uploaded resource planner files.

        Uses truncate-before-insert to prevent duplicate rows when
        the same file (or a replacement) is re-uploaded.
        """
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

        rp_total = None
        with st.status("Ingesting resource planner data...", expanded=True) as status:
            try:
                rp_total = 0
                if demand_file:
                    st.write(f"Saving `{demand_file.name}` to `files/resource/`...")
                    save_path = os.path.join(resource_dir, demand_file.name)
                    with open(save_path, "wb") as f:
                        f.write(demand_file.read())
                    demand_file.seek(0)
                    st.write("Clearing existing demand data and re-ingesting...")
                    df = parse_bpafg_demand(save_path)
                    n = insert_bpafg_to_db(df, cur, use_postgres=True, truncate_first=True)
                    rp_total += n
                    st.write(f"Replaced demand data with **{n}** rows from `{demand_file.name}`.")

                if priority_file:
                    st.write(f"Saving `{priority_file.name}` to `files/resource/`...")
                    save_path = os.path.join(resource_dir, priority_file.name)
                    with open(save_path, "wb") as f:
                        f.write(priority_file.read())
                    priority_file.seek(0)
                    st.write("Clearing existing priority data and re-ingesting...")
                    df = parse_priority_template(save_path)
                    n = insert_priority_to_db(df, cur, use_postgres=True, truncate_first=True)
                    rp_total += n
                    st.write(f"Replaced priority data with **{n}** rows from `{priority_file.name}`.")

                conn.commit()
                st.cache_data.clear()
                status.update(label="Resource planner data ingested successfully!", state="complete")

            except Exception as e:
                rp_total = None
                conn.rollback()
                status.update(label="Ingestion failed!", state="error")
                st.error(f"Ingest error: {e}")
                logger.exception(e)
            finally:
                conn.close()

        if rp_total is not None:
            self._celebrate_ingestion(rp_total, "Resource Planner")

    def _run_rp_reingest(self):
        """Re-ingest all files from ../files/resource/ (truncates tables first)."""
        rp_n = None
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
                    st.write("Clearing existing data and re-ingesting all files...")
                    rp_n = ingest_all(resource_dir, conn.cursor(), use_postgres=True,
                                      truncate_first=True)
                    conn.commit()
                    st.write(f"Replaced all resource planner data with **{rp_n}** total rows.")
                    st.cache_data.clear()
                    status.update(label=f"Re-ingested {rp_n} rows from files/resource/", state="complete")
                finally:
                    conn.close()
            except Exception as e:
                rp_n = None
                status.update(label="Re-ingestion failed!", state="error")
                st.error(f"Re-ingest error: {e}")
                logger.exception(e)

        if rp_n is not None:
            self._celebrate_ingestion(rp_n, "Resource Planner")

    # =====================================================================
    # Headcount section
    # =====================================================================
    def _render_headcount_section(self):
        st.subheader("Headcount Data")
        st.markdown(
            "Upload headcount data files (CSV/XLSX) for workforce analytics. "
            "Data is stored in the `headcount_data` table in PostgreSQL."
        )
        st.info(
            "**Note:** Uploading new files **replaces** all existing headcount data "
            "to prevent duplicate rows. The file on disk is also overwritten if it has the same name.",
            icon="ℹ️",
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
        """Save and ingest headcount CSV/XLSX files.
        Truncates existing data before first file to prevent duplicates."""
        import pandas as pd

        hc_dir = os.path.join("..", "files", "headcount")
        os.makedirs(hc_dir, exist_ok=True)

        hc_total = None
        with st.status("Ingesting headcount data...", expanded=True) as status:
            try:
                hc_total = 0
                st.write("Clearing existing headcount data and re-ingesting...")
                for i, f in enumerate(uploaded_files):
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

                    # Truncate only before first file
                    n = self._insert_headcount_to_db(df, truncate_first=(i == 0))
                    hc_total += n
                    st.write(f"Ingested **{n}** rows from `{f.name}`")

                st.cache_data.clear()
                status.update(label=f"Headcount: replaced with {hc_total} total rows!", state="complete")

            except Exception as e:
                hc_total = None
                status.update(label="Headcount ingestion failed!", state="error")
                st.error(f"Headcount ingest error: {e}")
                logger.exception(e)

        if hc_total is not None:
            self._celebrate_ingestion(hc_total, "Headcount")

    def _run_headcount_reingest(self):
        """Re-ingest all headcount files from ../files/headcount/ (truncates first)."""
        import pandas as pd

        hc_dir = os.path.join("..", "files", "headcount")
        if not os.path.exists(hc_dir):
            st.warning("No `files/headcount/` directory found. Upload files first.")
            return

        hc_n = None
        with st.status("Re-ingesting headcount data from files/headcount/...", expanded=True) as status:
            try:
                hc_n = 0
                files = [f for f in os.listdir(hc_dir) if f.endswith((".csv", ".xlsx", ".xls"))]
                if not files:
                    hc_n = None
                    st.warning("No CSV/XLSX files found in files/headcount/")
                    status.update(label="No files found", state="error")
                    return

                st.write("Clearing existing headcount data and re-ingesting all files...")
                for i, fname in enumerate(files):
                    fpath = os.path.join(hc_dir, fname)
                    st.write(f"Processing `{fname}`...")
                    if fname.endswith(".csv"):
                        df = pd.read_csv(fpath)
                    else:
                        df = pd.read_excel(fpath)
                    # Truncate only before first file
                    n = self._insert_headcount_to_db(df, truncate_first=(i == 0))
                    hc_n += n
                    st.write(f"Ingested **{n}** rows from `{fname}`")

                st.cache_data.clear()
                status.update(label=f"Replaced headcount data with {hc_n} rows", state="complete")

            except Exception as e:
                hc_n = None
                status.update(label="Re-ingestion failed!", state="error")
                st.error(f"Headcount re-ingest error: {e}")
                logger.exception(e)

        if hc_n is not None:
            self._celebrate_ingestion(hc_n, "Headcount")

    @staticmethod
    def _insert_headcount_to_db(df, truncate_first: bool = False) -> int:
        """Insert a headcount DataFrame into the headcount_data table.
        Creates the table dynamically based on the DataFrame columns.

        Args:
            truncate_first: If True, truncate existing data before inserting
                to prevent duplicate rows on re-upload.
        """
        from sqlalchemy import text
        from utils.models.database import OpexDB

        import pandas as pd

        # Normalize column names — strip everything except alphanumeric and underscores
        # (headcount CSVs often have #, /, (), etc. which break SQLAlchemy bind params)
        import re
        clean = []
        for c in df.columns:
            name = c.strip().lower()
            name = re.sub(r'[^a-z0-9]+', '_', name)  # replace any non-alnum run with _
            name = name.strip('_')                     # trim leading/trailing _
            if not name or name[0].isdigit():
                name = f"col_{name}"                   # prefix if empty or starts with digit
            clean.append(name)
        # De-duplicate column names (append _2, _3, etc.)
        seen = {}
        for i, name in enumerate(clean):
            if name in seen:
                seen[name] += 1
                clean[i] = f"{name}_{seen[name]}"
            else:
                seen[name] = 1
        df.columns = clean

        # Detect column types BEFORE None replacement (which can change dtypes)
        col_types = {}
        for col in df.columns:
            dtype = df[col].dtype
            if pd.api.types.is_integer_dtype(dtype):
                col_types[col] = "INTEGER"
            elif pd.api.types.is_float_dtype(dtype):
                col_types[col] = "DOUBLE PRECISION"
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                col_types[col] = "TIMESTAMP"
            else:
                col_types[col] = "TEXT"

        # Convert DataFrame to records and scrub ALL null-like values to Python None.
        # pandas NaT, NaN, numpy.nan survive df.where() and to_dict() as objects
        # that PostgreSQL rejects as literal strings 'NaT' / 'NaN'.
        import numpy as np
        import math

        def _scrub_value(v):
            """Convert any null-like value to None for safe SQL insertion."""
            if v is None:
                return None
            if isinstance(v, float) and (math.isnan(v) or np.isnan(v)):
                return None
            if isinstance(v, type(pd.NaT)):
                return None
            if hasattr(v, 'isoformat'):
                # Convert pandas Timestamp / datetime to Python datetime for psycopg2
                try:
                    return v.to_pydatetime() if hasattr(v, 'to_pydatetime') else v
                except Exception:
                    return str(v)
            return v

        records = []
        for row_dict in df.to_dict(orient="records"):
            records.append({k: _scrub_value(v) for k, v in row_dict.items()})

        with OpexDB.engine.begin() as conn:
            # Create table if not exists — dynamic schema from DataFrame
            cols_sql = [f'"{col}" {col_types[col]}' for col in df.columns]

            create_sql = f"""
                CREATE TABLE IF NOT EXISTS headcount_data (
                    id SERIAL PRIMARY KEY,
                    {', '.join(cols_sql)}
                )
            """
            conn.execute(text(create_sql))

            # Truncate before inserting to prevent duplicates
            if truncate_first:
                conn.execute(text("TRUNCATE TABLE headcount_data RESTART IDENTITY"))

            # Insert rows
            if records:
                col_names = ', '.join([f'"{c}"' for c in df.columns])
                placeholders = ', '.join([f':{c}' for c in df.columns])
                insert_sql = f"INSERT INTO headcount_data ({col_names}) VALUES ({placeholders})"
                conn.execute(text(insert_sql), records)

        return len(records)

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

    @staticmethod
    def _celebrate_ingestion(row_count: int, label: str = "Data"):
        """Show a fun celebration animation with $$ signs floating up like balloons."""
        import random

        # Generate 20 floating $$ elements with random positions, sizes, and timing
        symbols = []
        for i in range(20):
            left = random.randint(2, 95)
            delay = round(random.uniform(0, 2.5), 2)
            duration = round(random.uniform(2.5, 5.0), 2)
            size = random.choice(["1.2rem", "1.6rem", "2.0rem", "2.5rem", "3.0rem"])
            opacity = round(random.uniform(0.5, 1.0), 2)
            wobble = random.randint(-40, 40)
            symbol = random.choice(["$$", "$", "$$"])
            color = random.choice(["#2E7D32", "#1B5E20", "#4CAF50", "#8B6914", "#B8860B", "#FFD700"])
            symbols.append(
                f'<span class="fira-float" style="'
                f"left:{left}%; animation-delay:{delay}s; animation-duration:{duration}s; "
                f'font-size:{size}; opacity:{opacity}; --wobble:{wobble}px; color:{color};'
                f'">{symbol}</span>'
            )

        animation_html = f"""
        <style>
            @keyframes fira-rise {{
                0%   {{ transform: translateY(0) translateX(0) rotate(0deg); opacity: 0; }}
                10%  {{ opacity: 1; }}
                50%  {{ transform: translateY(-200px) translateX(var(--wobble, 20px)) rotate(15deg); opacity: 0.9; }}
                100% {{ transform: translateY(-420px) translateX(calc(var(--wobble, 20px) * -1)) rotate(-10deg); opacity: 0; }}
            }}
            .fira-celebrate-box {{
                position: relative;
                height: 180px;
                overflow: hidden;
                border-radius: 12px;
                background: linear-gradient(135deg, #E8F5E9 0%, #FFF8E1 50%, #E8F5E9 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0.5rem 0 1rem;
                border: 2px solid #4CAF50;
            }}
            .fira-celebrate-text {{
                text-align: center;
                z-index: 10;
                position: relative;
            }}
            .fira-celebrate-text h2 {{
                margin: 0;
                font-size: 1.8rem;
                color: #1B5E20;
                text-shadow: 0 1px 2px rgba(0,0,0,0.1);
            }}
            .fira-celebrate-text p {{
                margin: 4px 0 0;
                font-size: 1.1rem;
                color: #555;
            }}
            .fira-float {{
                position: absolute;
                bottom: -30px;
                font-weight: bold;
                animation: fira-rise ease-out forwards;
                pointer-events: none;
                z-index: 5;
                text-shadow: 0 1px 3px rgba(0,0,0,0.15);
            }}
        </style>
        <div class="fira-celebrate-box">
            <div class="fira-celebrate-text">
                <h2>{label} Ingestion Complete!</h2>
                <p><strong>{row_count:,}</strong> rows loaded successfully</p>
            </div>
            {''.join(symbols)}
        </div>
        """
        st.markdown(animation_html, unsafe_allow_html=True)
