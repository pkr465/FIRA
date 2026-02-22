"""
FIRA Resource Planner — CSV / XLSX Parser

Parses two data sources and stores them in the database:
  1. BPAFG demand CSV/XLSX  (resource-level monthly demand)
  2. Priority template CSV/XLSX  (project priority, country capacity, costs)

Handles both .csv and .xlsx formats transparently.
"""

import logging
import os
import re
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Month normalisation helpers
# ---------------------------------------------------------------------------

_MONTH_ABBR = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

def _normalise_month_header(raw: str) -> Optional[str]:
    """
    Convert varied month headers to a canonical 'Mon YY' form.
    Handles: ="Oct 25", Oct 25, 25-Oct, 2025-10, Oct-25, etc.
    Returns None if not a recognisable month column.
    """
    s = raw.strip().strip('="').strip('"').strip("'").strip()
    if not s:
        return None

    # Pattern: Mon YY  (e.g. "Oct 25")
    m = re.match(r'^([A-Za-z]{3})\s*[-/]?\s*(\d{2,4})$', s)
    if m:
        mon, yr = m.group(1).lower(), m.group(2)
        if mon in _MONTH_ABBR:
            yr = yr[-2:] if len(yr) == 4 else yr
            return f"{mon.capitalize()} {yr}"

    # Pattern: YY-Mon  (e.g. "25-Oct")
    m = re.match(r'^(\d{2,4})\s*[-/]\s*([A-Za-z]{3})$', s)
    if m:
        yr, mon = m.group(1), m.group(2).lower()
        if mon in _MONTH_ABBR:
            yr = yr[-2:] if len(yr) == 4 else yr
            return f"{mon.capitalize()} {yr}"

    # Pattern: YYYY-MM  (e.g. "2025-10")
    m = re.match(r'^(\d{4})-(\d{2})$', s)
    if m:
        yr, mo = m.group(1), m.group(2)
        rev = {v: k for k, v in _MONTH_ABBR.items()}
        if mo in rev:
            return f"{rev[mo].capitalize()} {yr[-2:]}"

    # Pattern: Mon-YY  (e.g. "Feb-29")
    m = re.match(r'^([A-Za-z]{3})-(\d{2})$', s)
    if m:
        mon, yr = m.group(1).lower(), m.group(2)
        if mon in _MONTH_ABBR:
            return f"{mon.capitalize()} {yr}"

    return None


# ---------------------------------------------------------------------------
# File reader (CSV or XLSX)
# ---------------------------------------------------------------------------

def read_tabular_file(filepath: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """Read a .csv, .tsv, or .xlsx file into a DataFrame."""
    ext = Path(filepath).suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(filepath, encoding="utf-8-sig")
    elif ext == ".tsv":
        df = pd.read_csv(filepath, sep="\t", encoding="utf-8-sig")
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(filepath, sheet_name=sheet_name or 0, engine="openpyxl")
    else:
        raise ValueError(f"Unsupported file format: {ext}")

    # Clean column names: strip whitespace, remove leading =" wrappers
    df.columns = [
        str(c).strip().strip('="').strip('"').strip("'").strip()
        for c in df.columns
    ]
    return df


# ---------------------------------------------------------------------------
# BPAFG Demand Parser
# ---------------------------------------------------------------------------

def parse_bpafg_demand(filepath: str) -> pd.DataFrame:
    """
    Parse a BPAFG demand file (CSV or XLSX) into a long-form DataFrame.

    Expected columns:
        Resource Name, Project Name, Task Name, HOMEGROUP,
        Resource Security Group, PRIMARY_BL, DEPT_COUNTRY, DEMAND_TYPE,
        <month columns...>

    Returns a DataFrame with columns:
        resource_name, project_name, task_name, homegroup,
        resource_security_group, primary_bl, dept_country, demand_type,
        month, value, source_file
    """
    df = read_tabular_file(filepath)
    logger.info(f"BPAFG: read {len(df)} rows, {len(df.columns)} columns from {filepath}")

    # Identify metadata vs month columns
    meta_cols_map = {
        "Resource Name": "resource_name",
        "Project Name": "project_name",
        "Task Name": "task_name",
        "HOMEGROUP": "homegroup",
        "Resource Security Group": "resource_security_group",
        "PRIMARY_BL": "primary_bl",
        "DEPT_COUNTRY": "dept_country",
        "DEMAND_TYPE": "demand_type",
    }

    # Map actual columns to canonical names
    actual_meta = {}
    for col in df.columns:
        for key, canonical in meta_cols_map.items():
            if col.lower().replace("_", " ") == key.lower().replace("_", " "):
                actual_meta[col] = canonical
                break

    # Identify month columns
    month_cols = {}
    for col in df.columns:
        if col in actual_meta:
            continue
        norm = _normalise_month_header(col)
        if norm:
            month_cols[col] = norm

    if not month_cols:
        logger.warning("No month columns detected in BPAFG file!")
        return pd.DataFrame()

    logger.info(f"BPAFG: found {len(actual_meta)} metadata cols, {len(month_cols)} month cols")

    # Melt to long form
    id_vars = list(actual_meta.keys())
    value_vars = list(month_cols.keys())

    df_long = df.melt(
        id_vars=id_vars,
        value_vars=value_vars,
        var_name="raw_month",
        value_name="value",
    )

    # Rename meta columns
    df_long = df_long.rename(columns=actual_meta)

    # Normalise month names
    df_long["month"] = df_long["raw_month"].map(month_cols)
    df_long = df_long.drop(columns=["raw_month"])

    # Clean values
    df_long["value"] = pd.to_numeric(df_long["value"], errors="coerce").fillna(0)
    df_long["source_file"] = os.path.basename(filepath)

    # Drop rows where all values are zero and no project
    df_long = df_long[~((df_long["value"] == 0) & df_long["project_name"].isna())]

    logger.info(f"BPAFG: parsed {len(df_long)} long-form rows")
    return df_long


# ---------------------------------------------------------------------------
# Priority Template Parser
# ---------------------------------------------------------------------------

def parse_priority_template(filepath: str) -> pd.DataFrame:
    """
    Parse a priority template file (CSV or XLSX).

    Expected columns (case-insensitive):
        Project, Priority, Country, Target Capacity, Country Cost,
        Month, Monthly Capacity,
        <month columns for monthly capacity values...>

    Returns a DataFrame with columns:
        project, priority, country, target_capacity, country_cost,
        month, monthly_capacity, source_file
    """
    df = read_tabular_file(filepath)
    logger.info(f"Priority: read {len(df)} rows, {len(df.columns)} columns from {filepath}")

    col_lower = {c: c.lower().strip() for c in df.columns}

    # Map canonical names
    col_map = {}
    for orig, low in col_lower.items():
        if low in ("project", "project name"):
            col_map[orig] = "project"
        elif low in ("priority", "rank", "order"):
            col_map[orig] = "priority"
        elif low == "country":
            col_map[orig] = "country"
        elif low in ("target capacity", "capacity", "hc target"):
            col_map[orig] = "target_capacity"
        elif low in ("country cost", "cost", "cost multiplier", "cost per hc"):
            col_map[orig] = "country_cost"
        elif low in ("month",):
            col_map[orig] = "month_col"
        elif low in ("monthly capacity", "monthlycap", "monthly hc"):
            col_map[orig] = "monthly_capacity"

    # Identify month-value columns (e.g., 25-Oct, Jan 26, etc.)
    month_value_cols = {}
    for col in df.columns:
        if col in col_map:
            continue
        norm = _normalise_month_header(col)
        if norm:
            month_value_cols[col] = norm

    df_renamed = df.rename(columns=col_map)

    results = []
    source = os.path.basename(filepath)

    if month_value_cols:
        # Has wide-format monthly capacity columns — melt them
        meta_cols_present = [c for c in ["project", "priority", "country", "target_capacity", "country_cost"] if c in df_renamed.columns]

        for _, row in df_renamed.iterrows():
            base = {mc: row.get(mc) for mc in meta_cols_present}
            base["source_file"] = source

            for orig_col, norm_month in month_value_cols.items():
                val = row.get(orig_col)
                entry = base.copy()
                entry["month"] = norm_month
                entry["monthly_capacity"] = pd.to_numeric(val, errors="coerce") if pd.notna(val) else None
                results.append(entry)
    else:
        # Long format with Month and Monthly Capacity columns
        for _, row in df_renamed.iterrows():
            entry = {
                "project": row.get("project"),
                "priority": row.get("priority"),
                "country": row.get("country"),
                "target_capacity": row.get("target_capacity"),
                "country_cost": row.get("country_cost"),
                "month": row.get("month_col"),
                "monthly_capacity": row.get("monthly_capacity"),
                "source_file": source,
            }
            results.append(entry)

    df_out = pd.DataFrame(results)

    # Clean numeric columns
    for col in ["priority", "target_capacity", "country_cost", "monthly_capacity"]:
        if col in df_out.columns:
            df_out[col] = pd.to_numeric(df_out[col], errors="coerce")

    # Normalise month if present
    if "month" in df_out.columns:
        def try_norm(v):
            if pd.isna(v) or v is None:
                return None
            n = _normalise_month_header(str(v))
            return n if n else str(v)
        df_out["month"] = df_out["month"].apply(try_norm)

    logger.info(f"Priority: parsed {len(df_out)} rows")
    return df_out


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------

def insert_bpafg_to_db(df: pd.DataFrame, cursor, use_postgres: bool = True):
    """Insert BPAFG demand data into the bpafg_demand table."""
    if df.empty:
        logger.warning("No BPAFG data to insert.")
        return 0

    placeholder = "%s" if use_postgres else "?"

    sql = f"""
        INSERT INTO bpafg_demand
            (resource_name, project_name, task_name, homegroup,
             resource_security_group, primary_bl, dept_country, demand_type,
             month, value, source_file)
        VALUES ({', '.join([placeholder] * 11)})
    """

    rows = []
    for _, r in df.iterrows():
        rows.append((
            r.get("resource_name"), r.get("project_name"), r.get("task_name"),
            r.get("homegroup"), r.get("resource_security_group"),
            r.get("primary_bl"), r.get("dept_country"), r.get("demand_type"),
            r.get("month"), float(r.get("value", 0)), r.get("source_file"),
        ))

    cursor.executemany(sql, rows)
    logger.info(f"Inserted {len(rows)} rows into bpafg_demand.")
    return len(rows)


def insert_priority_to_db(df: pd.DataFrame, cursor, use_postgres: bool = True):
    """Insert priority template data into the priority_template table."""
    if df.empty:
        logger.warning("No priority data to insert.")
        return 0

    placeholder = "%s" if use_postgres else "?"

    sql = f"""
        INSERT INTO priority_template
            (project, priority, country, target_capacity, country_cost,
             month, monthly_capacity, source_file)
        VALUES ({', '.join([placeholder] * 8)})
    """

    rows = []
    for _, r in df.iterrows():
        rows.append((
            r.get("project"),
            int(r["priority"]) if pd.notna(r.get("priority")) else None,
            r.get("country"),
            float(r["target_capacity"]) if pd.notna(r.get("target_capacity")) else None,
            float(r["country_cost"]) if pd.notna(r.get("country_cost")) else None,
            r.get("month"),
            float(r["monthly_capacity"]) if pd.notna(r.get("monthly_capacity")) else None,
            r.get("source_file"),
        ))

    cursor.executemany(sql, rows)
    logger.info(f"Inserted {len(rows)} rows into priority_template.")
    return len(rows)


# ---------------------------------------------------------------------------
# High-level ingest functions
# ---------------------------------------------------------------------------

def ingest_bpafg_file(filepath: str, cursor, use_postgres: bool = True) -> int:
    """Parse + insert a BPAFG demand file."""
    df = parse_bpafg_demand(filepath)
    return insert_bpafg_to_db(df, cursor, use_postgres)


def ingest_priority_file(filepath: str, cursor, use_postgres: bool = True) -> int:
    """Parse + insert a priority template file."""
    df = parse_priority_template(filepath)
    return insert_priority_to_db(df, cursor, use_postgres)


def ingest_all(data_dir: str = "../files/resource", cursor=None, use_postgres: bool = True):
    """
    Scan data_dir for BPAFG and priority files, parse and ingest them.
    Recognises files by name patterns.
    """
    data_path = Path(data_dir)
    if not data_path.exists():
        logger.error(f"Data directory not found: {data_dir}")
        return

    total = 0
    for fpath in sorted(data_path.glob("*")):
        ext = fpath.suffix.lower()
        if ext not in (".csv", ".xlsx", ".xls", ".tsv"):
            continue

        name_lower = fpath.name.lower()
        if "bpafg" in name_lower:
            logger.info(f"Ingesting BPAFG file: {fpath.name}")
            total += ingest_bpafg_file(str(fpath), cursor, use_postgres)
        elif "priority" in name_lower:
            logger.info(f"Ingesting Priority file: {fpath.name}")
            total += ingest_priority_file(str(fpath), cursor, use_postgres)
        else:
            logger.debug(f"Skipping unrecognised file: {fpath.name}")

    logger.info(f"Total rows ingested: {total}")
    return total


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sqlite3

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="Parse FIRA data files and store in database.")
    parser.add_argument("--data-dir", default="../files/resource", help="Directory containing CSV/XLSX files")
    parser.add_argument("--db", default="postgres", choices=["sqlite", "postgres"], help="Database backend")
    parser.add_argument("--db-path", default="../files/resource/cbn_resource_planner.db", help="SQLite DB path")
    parser.add_argument("--config", default="config/config.yaml", help="Postgres config path")
    args = parser.parse_args()

    if args.db == "sqlite":
        from db.cbn_tables import setup_tables_sqlite
        setup_tables_sqlite(args.db_path)
        conn = sqlite3.connect(args.db_path)
        try:
            ingest_all(args.data_dir, conn.cursor(), use_postgres=False)
            conn.commit()
        finally:
            conn.close()
    else:
        from db.cbn_tables import setup_tables_postgres, get_pg_connection
        setup_tables_postgres(args.config)
        conn = get_pg_connection(args.config)
        try:
            ingest_all(args.data_dir, conn.cursor(), use_postgres=True)
            conn.commit()
        finally:
            conn.close()

    print("Done.")
