"""
FIRA Resource Planner — Streamlit Page

Mirrors the full functionality of the Resource Planner POC:
  - Filters (Country, Project, Homegroup, Primary BL, Demand Type)
  - Target Capacity panel (per-country editable inputs + monthly toggle)
  - Project Order panel (drag-and-drop reordering)
  - Cost panel (per-country cost multiplier, toggle cost view)
  - Mountain Chart (Plotly stacked area with axis controls)
  - Project Allocation table (editable values, shift controls, search)
  - Download CSV, Save/Load snapshots

All data is loaded from PostgreSQL (or SQLite fallback).
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import logging
import json
import os
import re
from typing import Dict, List, Optional, Tuple
from collections import OrderedDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database connection helper
# ---------------------------------------------------------------------------

def _get_db_connection():
    """Get a PostgreSQL database connection for FIRA Resource Planner."""
    try:
        from db.cbn_tables import get_pg_connection
        conn = get_pg_connection()
        conn.cursor().execute("SELECT 1")
        return conn, True
    except Exception as e:
        logger.error(f"PostgreSQL connection failed: {e}")
        return None, False


def _execute_query(sql: str, params=None) -> pd.DataFrame:
    """Execute a query and return a DataFrame."""
    conn, is_pg = _get_db_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        if params:
            return pd.read_sql_query(sql, conn, params=params)
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Data loading functions
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def load_demand_data() -> pd.DataFrame:
    """Load all demand data from bpafg_demand table."""
    return _execute_query("SELECT * FROM bpafg_demand")


@st.cache_data(ttl=300)
def load_priority_data() -> pd.DataFrame:
    """Load all priority template data."""
    return _execute_query("SELECT * FROM priority_template")


@st.cache_data(ttl=300)
def load_filter_options() -> dict:
    """Load distinct filter values."""
    df = load_demand_data()
    if df.empty:
        return {k: ["All"] for k in ["dept_country", "project_name", "homegroup", "primary_bl", "demand_type"]}

    opts = {}
    for col in ["dept_country", "project_name", "homegroup", "primary_bl", "demand_type"]:
        if col in df.columns:
            vals = sorted(df[col].dropna().unique().tolist())
            opts[col] = ["All"] + vals
        else:
            opts[col] = ["All"]
    return opts


def get_demand_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate demand and pivot to wide format:
    Rows = (project_name, dept_country), Columns = month, Values = sum of value
    """
    if df.empty:
        return pd.DataFrame()

    agg = df.groupby(["project_name", "dept_country", "month"])["value"].sum().reset_index()
    pivot = agg.pivot_table(
        index=["project_name", "dept_country"],
        columns="month",
        values="value",
        aggfunc="sum",
        fill_value=0,
    )

    # Sort month columns chronologically
    month_order = _sort_months(pivot.columns.tolist())
    pivot = pivot.reindex(columns=month_order, fill_value=0)
    pivot = pivot.reset_index()
    return pivot


def _sort_months(months: list) -> list:
    """Sort month strings like 'Oct 25', 'Nov 25' chronologically."""
    month_num = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    def sort_key(m):
        parts = m.strip().split()
        if len(parts) == 2:
            mon = parts[0].lower()[:3]
            yr = int(parts[1]) if parts[1].isdigit() else 0
            if yr < 100:
                yr += 2000
            return (yr, month_num.get(mon, 0))
        return (9999, 0)

    return sorted(months, key=sort_key)


# ---------------------------------------------------------------------------
# Mountain Chart builder
# ---------------------------------------------------------------------------

def build_mountain_chart(
    pivot_df: pd.DataFrame,
    project_order: list,
    capacity_line: dict,
    month_columns: list,
    y_min: Optional[float] = None,
    y_max: Optional[float] = None,
    x_start: Optional[str] = None,
    x_end: Optional[str] = None,
    show_gap_markers: bool = True,
    selected_projects: list = None,
) -> go.Figure:
    """
    Build a Plotly stacked area (mountain) chart.

    pivot_df: wide-form demand (project_name, dept_country, month cols)
    project_order: list of project names in stack order
    capacity_line: {month: capacity_value} for the capacity line
    """
    fig = go.Figure()

    if pivot_df.empty or not month_columns:
        fig.add_annotation(text="No data — upload a demand CSV or check filters.", showarrow=False)
        return fig

    # Determine x-axis range
    if x_start and x_start in month_columns:
        start_idx = month_columns.index(x_start)
    else:
        start_idx = 0
    if x_end and x_end in month_columns:
        end_idx = month_columns.index(x_end) + 1
    else:
        end_idx = len(month_columns)

    visible_months = month_columns[start_idx:end_idx]

    # Aggregate by project (sum across countries)
    proj_agg = pivot_df.groupby("project_name")[month_columns].sum()

    # High-contrast multi-color palette for light background
    colors = [
        "#1B5E20", "#0D47A1", "#E65100", "#6A1B9A", "#00838F",
        "#C62828", "#2E7D32", "#4527A0", "#EF6C00", "#00695C",
        "#AD1457", "#1565C0", "#F9A825", "#283593", "#558B2F",
        "#4E342E", "#00796B", "#D84315", "#5C6BC0", "#827717",
        "#37474F", "#880E4F", "#01579B", "#BF360C", "#1A237E",
        "#33691E", "#006064", "#B71C1C", "#311B92", "#FF6F00",
    ]

    # Add stacked area traces in project order
    ordered_projects = [p for p in project_order if p in proj_agg.index]
    remaining = [p for p in proj_agg.index if p not in ordered_projects]
    all_projects = ordered_projects + remaining

    for i, proj in enumerate(all_projects):
        if selected_projects and proj not in selected_projects:
            continue
        y_vals = proj_agg.loc[proj, visible_months].values.astype(float)
        color = colors[i % len(colors)]

        fig.add_trace(go.Scatter(
            x=visible_months,
            y=y_vals,
            name=proj,
            mode="lines",
            line=dict(width=0.5, color=color),
            fill="tonexty" if i > 0 else "tozeroy",
            fillcolor=color.replace(")", ",0.6)").replace("rgb", "rgba") if "rgb" in color else color,
            stackgroup="demand",
            hovertemplate=f"<b>{proj}</b><br>Month: %{{x}}<br>HC: %{{y:.2f}}<extra></extra>",
        ))

    # Capacity line
    if capacity_line:
        cap_values = [capacity_line.get(m, 0) for m in visible_months]
        if any(v > 0 for v in cap_values):
            fig.add_trace(go.Scatter(
                x=visible_months,
                y=cap_values,
                name="Capacity",
                mode="lines",
                line=dict(color="#8B6914", width=3, dash="dash"),
                hovertemplate="<b>Capacity</b><br>Month: %{x}<br>HC: %{y:.2f}<extra></extra>",
            ))

            # Gap markers
            if show_gap_markers:
                total_demand = proj_agg[visible_months].sum()
                for m_idx, month in enumerate(visible_months):
                    demand_val = total_demand[month] if month in total_demand.index else 0
                    cap_val = capacity_line.get(month, 0)
                    if demand_val > cap_val and cap_val > 0:
                        fig.add_vline(
                            x=m_idx, line_width=1, line_dash="dot",
                            line_color="rgba(239, 83, 80, 0.45)",
                        )

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#F1F8F1",
        plot_bgcolor="#FFFFFF",
        height=max(500, 70 * len(visible_months) // 10 + 300),
        margin=dict(l=60, r=20, t=40, b=60),
        font=dict(family="IBM Plex Sans, sans-serif", color="#1A2E1A"),
        xaxis=dict(
            title=dict(text="Month", font=dict(color="#4A6B4A")),
            tickangle=-45,
            tickfont=dict(color="#4A6B4A"),
            gridcolor="#E0F0E0",
            zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="Headcount (HC)", font=dict(color="#4A6B4A")),
            range=[y_min, y_max] if y_min is not None or y_max is not None else None,
            tickfont=dict(color="#4A6B4A", family="IBM Plex Mono, monospace"),
            gridcolor="#E0F0E0",
            zeroline=False,
        ),
        legend=dict(
            orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5,
            font=dict(size=10, color="#1A2E1A"),
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#C8DCC8",
            borderwidth=1,
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#FFFFFF",
            bordercolor="#2E7D32",
            font=dict(color="#1A2E1A", family="IBM Plex Mono, monospace"),
        ),
    )

    return fig


# ---------------------------------------------------------------------------
# Main Streamlit Page
# ---------------------------------------------------------------------------

class CBNResourcePlanner:
    """Streamlit page class for FIRA Resource Planner."""

    def __init__(self, title: str = "FIRA Resource Planner", url: str = "cbn_planner"):
        self.title = title
        self.url = url

    def render(self):
        """Render the full FIRA Resource Planner page."""

        # --- Inject finance theme CSS ---
        try:
            from ui.streamlit_tools import app_css
            app_css()
        except ImportError:
            pass

        # --- Header ---
        st.markdown(
            "<h1 style='text-align:center;'>FIRA Resource Planner</h1>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='text-align:center; color:#4A6B4A; font-style:italic; font-size:15px;'>"
            "Dynamic mountain charts, cost estimation & resource analysis from Tempus forecast data. "
            "Adjust capacity, reorder projects, apply filters, and explore what-if scenarios."
            "</p>",
            unsafe_allow_html=True,
        )

        # Load data
        demand_df = load_demand_data()
        priority_df = load_priority_data()
        filter_opts = load_filter_options()

        if demand_df.empty:
            st.warning(
                "No demand data found in the database. "
                "Run the parser first: `python -m utils.parsers.cbn_data_parser --data-dir ../files/resource --db postgres`"
            )
            self._render_upload_section()
            return

        # --- Initialize session state ---
        self._init_session_state(demand_df, priority_df)

        # ========== FILTERS ==========
        self._render_filters(filter_opts)

        # Apply filters to demand data
        filtered_df = self._apply_filters(demand_df)

        # Get month columns & pivot
        pivot_df = get_demand_pivot(filtered_df)
        if pivot_df.empty:
            st.info("No data matches current filters.")
            return

        month_cols = [c for c in pivot_df.columns if c not in ("project_name", "dept_country")]

        # ========== LAYOUT: Left sidebar + Right chart ==========
        left_col, right_col = st.columns([1, 3])

        with left_col:
            # --- Target Capacity Panel ---
            self._render_capacity_panel(month_cols)

            # --- Project Order Panel ---
            self._render_project_order_panel(pivot_df)

            # --- Cost Panel ---
            self._render_cost_panel()

        with right_col:
            # --- Mountain Chart ---
            self._render_mountain_chart(pivot_df, month_cols)

        # ========== PROJECT ALLOCATION TABLE (full width) ==========
        self._render_allocation_table(pivot_df, month_cols)

        # ========== DOWNLOAD / SNAPSHOT CONTROLS ==========
        self._render_controls(pivot_df, month_cols)

    # -------------------------------------------------------------------
    # Session state initialization
    # -------------------------------------------------------------------

    def _init_session_state(self, demand_df: pd.DataFrame, priority_df: pd.DataFrame):
        """Initialize session state with defaults."""

        if "cbn_initialized" not in st.session_state:
            # Project order from priority template
            if not priority_df.empty and "project" in priority_df.columns:
                projects = priority_df.dropna(subset=["project"])
                projects = projects[projects["project"] != ""]
                if "priority" in projects.columns:
                    projects = projects.sort_values("priority")
                st.session_state["project_order"] = projects["project"].unique().tolist()
            else:
                st.session_state["project_order"] = sorted(demand_df["project_name"].dropna().unique().tolist())

            # Country capacities from priority template
            caps = {}
            costs = {}
            if not priority_df.empty and "country" in priority_df.columns:
                for _, row in priority_df.dropna(subset=["country"]).iterrows():
                    c = row["country"]
                    if pd.notna(row.get("target_capacity")):
                        caps[c] = float(row["target_capacity"])
                    if pd.notna(row.get("country_cost")):
                        costs[c] = float(row["country_cost"])

            # Fill in countries from demand data
            for c in demand_df["dept_country"].dropna().unique():
                if c not in caps:
                    caps[c] = 0
                if c not in costs:
                    costs[c] = 0

            st.session_state["country_capacities"] = caps
            st.session_state["country_costs"] = costs
            st.session_state["show_cost"] = False
            st.session_state["monthly_cap_enabled"] = False
            st.session_state["monthly_caps"] = {}
            st.session_state["shift_values"] = {}
            st.session_state["cell_overrides"] = {}
            st.session_state["show_gap_markers"] = True
            st.session_state["hidden_projects"] = set()
            st.session_state["snapshots"] = []
            st.session_state["cbn_initialized"] = True

    # -------------------------------------------------------------------
    # FILTERS
    # -------------------------------------------------------------------

    def _render_filters(self, filter_opts: dict):
        """Render filter dropdowns in an expander."""
        with st.expander("Filters", expanded=True):
            cols = st.columns(5)

            labels = {
                "dept_country": "Country",
                "project_name": "Project",
                "homegroup": "Homegroup",
                "primary_bl": "Primary BL",
                "demand_type": "Demand Type",
            }

            for i, (key, label) in enumerate(labels.items()):
                with cols[i]:
                    options = filter_opts.get(key, ["All"])
                    st.selectbox(label, options, key=f"filter_{key}")

    def _apply_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply current filter selections to the DataFrame."""
        filtered = df.copy()
        filter_map = {
            "dept_country": "filter_dept_country",
            "project_name": "filter_project_name",
            "homegroup": "filter_homegroup",
            "primary_bl": "filter_primary_bl",
            "demand_type": "filter_demand_type",
        }
        for col, key in filter_map.items():
            val = st.session_state.get(key, "All")
            if val and val != "All" and col in filtered.columns:
                filtered = filtered[filtered[col] == val]
        return filtered

    # -------------------------------------------------------------------
    # TARGET CAPACITY PANEL
    # -------------------------------------------------------------------

    def _render_capacity_panel(self, month_cols: list):
        """Render target capacity inputs per country."""
        with st.expander("Target Capacity", expanded=True):
            st.caption("Enter desired capacity per country.")

            caps = st.session_state.get("country_capacities", {})
            monthly_enabled = st.checkbox(
                "Enable capacity by month",
                value=st.session_state.get("monthly_cap_enabled", False),
                key="monthly_cap_toggle",
            )
            st.session_state["monthly_cap_enabled"] = monthly_enabled

            total_cap = 0
            updated_caps = {}
            for country in sorted(caps.keys()):
                val = st.number_input(
                    country,
                    value=float(caps.get(country, 0)),
                    step=1.0,
                    min_value=0.0,
                    key=f"cap_{country}",
                )
                updated_caps[country] = val
                total_cap += val

            st.session_state["country_capacities"] = updated_caps
            st.metric("Total Capacity", f"{total_cap:.1f}")

            if monthly_enabled:
                st.info("Monthly capacity mode: capacity line will vary by month.")
                # Let user edit monthly caps for each country
                with st.expander("Edit Monthly Capacity"):
                    monthly_caps = st.session_state.get("monthly_caps", {})
                    for country in sorted(updated_caps.keys()):
                        st.subheader(country)
                        country_monthly = monthly_caps.get(country, {})
                        for month in month_cols[:6]:  # Show first 6 months for UI brevity
                            default = country_monthly.get(month, updated_caps.get(country, 0))
                            new_val = st.number_input(
                                f"{country} - {month}",
                                value=float(default),
                                step=1.0,
                                key=f"mcap_{country}_{month}",
                            )
                            if country not in monthly_caps:
                                monthly_caps[country] = {}
                            monthly_caps[country][month] = new_val
                    st.session_state["monthly_caps"] = monthly_caps

    # -------------------------------------------------------------------
    # PROJECT ORDER PANEL
    # -------------------------------------------------------------------

    def _render_project_order_panel(self, pivot_df: pd.DataFrame):
        """Render project ordering interface with hide/show toggle."""
        with st.expander("Project Order", expanded=False):
            st.caption("Reorder projects or hide them from the chart. Hidden projects are excluded from the mountain chart and totals.")

            # Search filter
            search = st.text_input("Search projects", key="proj_search", placeholder="Type to filter...")

            order = st.session_state.get("project_order", [])
            hidden = st.session_state.get("hidden_projects", set())
            available = pivot_df["project_name"].unique().tolist()
            # Add any new projects from data not in order
            for p in available:
                if p not in order:
                    order.append(p)

            # Filter display
            display_order = order
            if search:
                display_order = [p for p in order if search.lower() in p.lower()]

            # Action buttons
            btn_cols = st.columns(3)
            with btn_cols[0]:
                if st.button("Default Order", key="default_order"):
                    st.session_state["project_order"] = sorted(available)
                    st.rerun()
            with btn_cols[1]:
                if st.button("Show All", key="show_all_proj"):
                    st.session_state["hidden_projects"] = set()
                    st.rerun()
            with btn_cols[2]:
                hidden_count = len(hidden)
                if hidden_count > 0:
                    st.caption(f"{hidden_count} hidden")

            # Display projects with move + hide buttons
            for idx, proj in enumerate(display_order):
                real_idx = order.index(proj)
                is_hidden = proj in hidden
                col1, col2, col3, col4, col5, col6 = st.columns([4, 1, 1, 1, 1, 1])

                with col1:
                    label = f"{idx + 1}. {proj}"
                    if is_hidden:
                        st.markdown(f"<span style='color:#7A9A7A; text-decoration:line-through;'>{label}</span>",
                                    unsafe_allow_html=True)
                    else:
                        st.text(label)
                with col2:
                    if st.button("⬆", key=f"up_{proj}", help="Move up"):
                        if real_idx > 0:
                            order[real_idx], order[real_idx - 1] = order[real_idx - 1], order[real_idx]
                            st.session_state["project_order"] = order
                            st.rerun()
                with col3:
                    if st.button("⬇", key=f"down_{proj}", help="Move down"):
                        if real_idx < len(order) - 1:
                            order[real_idx], order[real_idx + 1] = order[real_idx + 1], order[real_idx]
                            st.session_state["project_order"] = order
                            st.rerun()
                with col4:
                    if st.button("⤒", key=f"top_{proj}", help="Move to top"):
                        order.remove(proj)
                        order.insert(0, proj)
                        st.session_state["project_order"] = order
                        st.rerun()
                with col5:
                    if st.button("⤓", key=f"bot_{proj}", help="Move to bottom"):
                        order.remove(proj)
                        order.append(proj)
                        st.session_state["project_order"] = order
                        st.rerun()
                with col6:
                    toggle_label = "👁" if is_hidden else "🙈"
                    toggle_help = "Show project" if is_hidden else "Hide project"
                    if st.button(toggle_label, key=f"hide_{proj}", help=toggle_help):
                        if is_hidden:
                            hidden.discard(proj)
                        else:
                            hidden.add(proj)
                        st.session_state["hidden_projects"] = hidden
                        st.rerun()

    # -------------------------------------------------------------------
    # COST PANEL
    # -------------------------------------------------------------------

    def _render_cost_panel(self):
        """Render cost multiplier inputs per country."""
        with st.expander("Cost", expanded=False):
            st.caption("Enter cost multiplier per country.")

            show_cost = st.checkbox(
                "Show cost in table",
                value=st.session_state.get("show_cost", False),
                key="cost_toggle",
            )
            st.session_state["show_cost"] = show_cost

            costs = st.session_state.get("country_costs", {})
            updated_costs = {}
            for country in sorted(costs.keys()):
                val = st.number_input(
                    f"{country} (cost/HC)",
                    value=float(costs.get(country, 0)),
                    step=0.5,
                    min_value=0.0,
                    key=f"cost_{country}",
                )
                updated_costs[country] = val

            st.session_state["country_costs"] = updated_costs

            if show_cost:
                total_cost = sum(
                    st.session_state["country_capacities"].get(c, 0) * v
                    for c, v in updated_costs.items()
                )
                st.metric("Estimated Total Cost", f"${total_cost:,.0f}K/month")

    # -------------------------------------------------------------------
    # MOUNTAIN CHART
    # -------------------------------------------------------------------

    def _render_mountain_chart(self, pivot_df: pd.DataFrame, month_cols: list):
        """Render the Plotly mountain chart with axis controls."""
        st.subheader("Mountain Chart")

        # Axis controls
        ax_cols = st.columns(6)
        with ax_cols[0]:
            y_min = st.number_input("Y Min", value=None, step=10, key="y_min", placeholder="auto")
        with ax_cols[1]:
            y_max = st.number_input("Y Max", value=None, step=10, key="y_max", placeholder="auto")
        with ax_cols[2]:
            x_start = st.selectbox("X Start", ["(auto)"] + month_cols, key="x_start")
        with ax_cols[3]:
            x_end = st.selectbox("X End", ["(auto)"] + month_cols, index=min(len(month_cols), len(month_cols)), key="x_end")
        with ax_cols[4]:
            show_gap = st.checkbox("Show months with gap", value=True, key="show_gap")
        with ax_cols[5]:
            if st.button("Reset Axes", key="reset_axes"):
                for k in ["y_min", "y_max"]:
                    st.session_state[k] = None
                st.rerun()

        # Build capacity line
        capacity_line = self._build_capacity_line(month_cols)

        # Apply shift overrides to pivot
        shifted_pivot = self._apply_shifts(pivot_df, month_cols)

        # Exclude hidden projects from chart
        hidden = st.session_state.get("hidden_projects", set())
        visible_projects = [p for p in st.session_state.get("project_order", []) if p not in hidden]

        fig = build_mountain_chart(
            pivot_df=shifted_pivot,
            project_order=visible_projects,
            capacity_line=capacity_line,
            month_columns=month_cols,
            y_min=y_min if y_min else None,
            y_max=y_max if y_max else None,
            x_start=x_start if x_start != "(auto)" else None,
            x_end=x_end if x_end != "(auto)" else None,
            show_gap_markers=show_gap,
            selected_projects=visible_projects,
        )

        st.plotly_chart(fig, use_container_width=True, key="mountain_chart")

    def _build_capacity_line(self, month_cols: list) -> dict:
        """Build capacity values per month for the chart."""
        caps = st.session_state.get("country_capacities", {})
        monthly_enabled = st.session_state.get("monthly_cap_enabled", False)
        monthly_caps = st.session_state.get("monthly_caps", {})

        total_cap = sum(caps.values())
        capacity_line = {}

        if monthly_enabled and monthly_caps:
            for month in month_cols:
                month_total = 0
                for country, mcaps in monthly_caps.items():
                    month_total += mcaps.get(month, caps.get(country, 0))
                capacity_line[month] = month_total
        else:
            for month in month_cols:
                capacity_line[month] = total_cap

        return capacity_line

    # -------------------------------------------------------------------
    # SHIFT LOGIC
    # -------------------------------------------------------------------

    def _apply_shifts(self, pivot_df: pd.DataFrame, month_cols: list) -> pd.DataFrame:
        """Apply project shift overrides."""
        shifts = st.session_state.get("shift_values", {})
        if not shifts:
            return pivot_df

        result = pivot_df.copy()
        for key, shift_val in shifts.items():
            if shift_val == 0:
                continue
            parts = key.rsplit("_", 1)
            if len(parts) != 2:
                continue
            proj, country = parts

            mask = (result["project_name"] == proj) & (result["dept_country"] == country)
            if not mask.any():
                continue

            row_idx = result[mask].index[0]
            values = result.loc[row_idx, month_cols].values.astype(float)

            if shift_val > 0:
                shifted = np.concatenate([np.zeros(shift_val), values[:-shift_val]])
            else:
                shifted = np.concatenate([values[-shift_val:], np.zeros(-shift_val)])

            result.loc[row_idx, month_cols] = shifted

        return result

    # -------------------------------------------------------------------
    # ALLOCATION TABLE
    # -------------------------------------------------------------------

    def _render_allocation_table(self, pivot_df: pd.DataFrame, month_cols: list):
        """Render the project allocation table with shift controls."""
        st.markdown("---")
        st.subheader("Project Allocation per Month")
        st.caption("Adjust allocations via shift controls. Use search to filter. Toggle cost mode in the left panel.")

        # Search
        table_search = st.text_input(
            "Search project or country",
            key="table_search",
            placeholder="Type to filter table rows...",
        )

        # Action buttons
        btn_cols = st.columns(7)
        with btn_cols[0]:
            if st.button("Reset to Original", key="reset_alloc"):
                st.session_state["shift_values"] = {}
                st.session_state["cell_overrides"] = {}
                st.rerun()
        with btn_cols[1]:
            download_csv = st.button("Download CSV", key="dl_csv")
        with btn_cols[2]:
            download_gap = st.button("Download Gap Summary", key="dl_gap")
        with btn_cols[3]:
            save_snap = st.button("Save Snapshot", key="save_snap")
        with btn_cols[4]:
            load_snap = st.button("Load Snapshot", key="load_snap")
        with btn_cols[5]:
            add_tbd = st.button("+ Add TBD Project", key="add_tbd")
        with btn_cols[6]:
            bulk_edit = st.button("Bulk Edit MM", key="bulk_edit")

        # Apply shifts
        shifted_pivot = self._apply_shifts(pivot_df, month_cols)

        # Exclude hidden projects
        hidden = st.session_state.get("hidden_projects", set())
        if hidden:
            shifted_pivot = shifted_pivot[~shifted_pivot["project_name"].isin(hidden)]

        # Filter by search
        display_df = shifted_pivot.copy()
        if table_search:
            mask = (
                display_df["project_name"].str.contains(table_search, case=False, na=False) |
                display_df["dept_country"].str.contains(table_search, case=False, na=False)
            )
            display_df = display_df[mask]

        # Show cost mode
        show_cost = st.session_state.get("show_cost", False)
        costs = st.session_state.get("country_costs", {})

        if show_cost and costs:
            for col in month_cols:
                display_df[col] = display_df.apply(
                    lambda row: row[col] * costs.get(row["dept_country"], 0),
                    axis=1,
                )

        # Shift controls as separate section
        with st.expander("Shift Controls", expanded=False):
            st.caption("Enter shift values per project-country pair to move allocations forward (+) or backward (-) by N months.")
            shifts = st.session_state.get("shift_values", {})

            for _, row in display_df.iterrows():
                proj = row["project_name"]
                country = row["dept_country"]
                key = f"{proj}_{country}"

                scols = st.columns([3, 1, 1, 1])
                with scols[0]:
                    st.text(f"{proj} — {country}")
                with scols[1]:
                    current_shift = shifts.get(key, 0)
                    st.text(f"Shift: {current_shift}")
                with scols[2]:
                    if st.button("+", key=f"shift_plus_{key}"):
                        shifts[key] = shifts.get(key, 0) + 1
                        st.session_state["shift_values"] = shifts
                        st.rerun()
                with scols[3]:
                    if st.button("−", key=f"shift_minus_{key}"):
                        shifts[key] = shifts.get(key, 0) - 1
                        st.session_state["shift_values"] = shifts
                        st.rerun()

        # Grand total row
        if not display_df.empty:
            total_row = display_df[month_cols].sum()
            grand_df = pd.DataFrame([["GRAND TOTAL", ""] + total_row.tolist()],
                                    columns=["project_name", "dept_country"] + month_cols)
            display_df = pd.concat([display_df, grand_df], ignore_index=True)

        # Capacity row
        capacity_line = self._build_capacity_line(month_cols)
        cap_row = pd.DataFrame([["CAPACITY", ""] + [capacity_line.get(m, 0) for m in month_cols]],
                               columns=["project_name", "dept_country"] + month_cols)
        display_df = pd.concat([display_df, cap_row], ignore_index=True)

        # Gap row
        if not display_df.empty:
            total_idx = display_df[display_df["project_name"] == "GRAND TOTAL"].index
            cap_idx = display_df[display_df["project_name"] == "CAPACITY"].index
            if len(total_idx) > 0 and len(cap_idx) > 0:
                gap_vals = display_df.loc[cap_idx[0], month_cols].values.astype(float) - \
                           display_df.loc[total_idx[0], month_cols].values.astype(float)
                gap_row = pd.DataFrame([["GAP (Cap - Demand)", ""] + gap_vals.tolist()],
                                       columns=["project_name", "dept_country"] + month_cols)
                display_df = pd.concat([display_df, gap_row], ignore_index=True)

        # Style the dataframe with Greenback Finance theme
        def _style_table(df):
            """Apply conditional formatting with finance color scheme."""
            styled = df.style.format(
                {col: "{:.2f}" for col in month_cols},
                na_rep="",
            )

            def highlight_gap(row):
                if row.get("project_name") == "GAP (Cap - Demand)":
                    return [
                        "background-color: #FFEBEE; color: #C62828; font-weight: bold"
                        if isinstance(v, (int, float)) and v < 0
                        else "background-color: #E8F5E9; color: #1B5E20; font-weight: bold"
                        if isinstance(v, (int, float)) and v >= 0
                        else ""
                        for v in row
                    ]
                if row.get("project_name") in ("GRAND TOTAL", "CAPACITY"):
                    return [
                        "font-weight: bold; background-color: #E8F5E9; color: #1B5E20; "
                        "border-top: 2px solid #2E7D32"
                    ] * len(row)
                return [""] * len(row)

            styled = styled.apply(highlight_gap, axis=1)
            return styled

        st.dataframe(
            _style_table(display_df),
            use_container_width=True,
            height=min(800, 50 + len(display_df) * 35),
        )

        # Handle downloads
        if download_csv:
            csv_data = shifted_pivot.to_csv(index=False)
            st.download_button(
                "Download Allocation CSV",
                csv_data,
                file_name="cbn_allocation.csv",
                mime="text/csv",
                key="actual_dl_csv",
            )

        if download_gap:
            gap_summary = self._compute_gap_summary(shifted_pivot, month_cols)
            st.download_button(
                "Download Gap Summary CSV",
                gap_summary.to_csv(index=False),
                file_name="cbn_gap_summary.csv",
                mime="text/csv",
                key="actual_dl_gap",
            )

        # Snapshot management
        if save_snap:
            snapshot = {
                "shift_values": st.session_state.get("shift_values", {}),
                "country_capacities": st.session_state.get("country_capacities", {}),
                "country_costs": st.session_state.get("country_costs", {}),
                "project_order": st.session_state.get("project_order", []),
                "hidden_projects": list(st.session_state.get("hidden_projects", set())),
            }
            st.session_state["snapshots"].append(snapshot)
            st.success(f"Snapshot #{len(st.session_state['snapshots'])} saved!")

        if load_snap:
            snapshots = st.session_state.get("snapshots", [])
            if snapshots:
                latest = snapshots[-1]
                st.session_state["shift_values"] = latest.get("shift_values", {})
                st.session_state["country_capacities"] = latest.get("country_capacities", {})
                st.session_state["country_costs"] = latest.get("country_costs", {})
                st.session_state["project_order"] = latest.get("project_order", [])
                st.session_state["hidden_projects"] = set(latest.get("hidden_projects", []))
                st.success("Snapshot loaded!")
                st.rerun()
            else:
                st.warning("No snapshots saved yet.")

        # Add TBD Project
        if add_tbd:
            st.session_state.setdefault("tbd_projects", [])
            tbd_name = f"TBD_Project_{len(st.session_state['tbd_projects']) + 1}"
            st.session_state["tbd_projects"].append(tbd_name)
            st.session_state["project_order"].append(tbd_name)
            st.success(f"Added {tbd_name}")

    def _compute_gap_summary(self, pivot_df: pd.DataFrame, month_cols: list) -> pd.DataFrame:
        """Compute gap summary by month (excludes hidden projects)."""
        capacity_line = self._build_capacity_line(month_cols)
        hidden = st.session_state.get("hidden_projects", set())
        visible_pivot = pivot_df[~pivot_df["project_name"].isin(hidden)] if hidden else pivot_df
        total_demand = visible_pivot[month_cols].sum()

        rows = []
        for month in month_cols:
            demand = total_demand.get(month, 0)
            capacity = capacity_line.get(month, 0)
            gap = capacity - demand
            rows.append({
                "Month": month,
                "Total Demand": round(demand, 2),
                "Capacity": round(capacity, 2),
                "Gap": round(gap, 2),
                "Status": "Over Capacity" if gap < 0 else "Under Capacity",
            })
        return pd.DataFrame(rows)

    # -------------------------------------------------------------------
    # CONTROLS & UPLOAD
    # -------------------------------------------------------------------

    def _render_controls(self, pivot_df: pd.DataFrame, month_cols: list):
        """Render the bottom control bar."""
        st.markdown("---")
        ctrl_cols = st.columns(3)
        with ctrl_cols[0]:
            st.caption(f"Data: {len(pivot_df)} project-country rows × {len(month_cols)} months")
        with ctrl_cols[1]:
            if st.button("Clear All Data Cache", key="clear_cache"):
                st.cache_data.clear()
                st.success("Cache cleared!")
        with ctrl_cols[2]:
            if st.button("Re-ingest Data Files", key="reingest"):
                self._run_ingest()

    def _render_upload_section(self):
        """Render file upload when no data exists."""
        st.markdown("### Upload Data Files")
        st.markdown("Upload your demand CSV and priority template CSV to get started.")

        col1, col2 = st.columns(2)
        with col1:
            demand_file = st.file_uploader(
                "Upload Demand CSV (BPAFG)",
                type=["csv", "xlsx"],
                key="upload_demand",
            )
        with col2:
            priority_file = st.file_uploader(
                "Upload Priority Template CSV",
                type=["csv", "xlsx"],
                key="upload_priority",
            )

        if st.button("Ingest Uploaded Files", key="ingest_uploaded"):
            if demand_file or priority_file:
                self._ingest_uploaded_files(demand_file, priority_file)
            else:
                st.warning("Please upload at least one file.")

    def _ingest_uploaded_files(self, demand_file, priority_file):
        """Parse and ingest uploaded files. Also saves copies to ../files/resource/."""
        from utils.parsers.cbn_data_parser import (
            parse_bpafg_demand, parse_priority_template,
            insert_bpafg_to_db, insert_priority_to_db,
        )

        # Ensure resource directory exists
        resource_dir = os.path.join("..", "files", "resource")
        os.makedirs(resource_dir, exist_ok=True)

        conn, is_pg = _get_db_connection()
        if conn is None:
            # Try to create tables and connect
            from db.cbn_tables import setup_tables_postgres, get_pg_connection
            try:
                setup_tables_postgres()
                conn = get_pg_connection()
                is_pg = True
            except Exception as e:
                st.error(f"Cannot connect to PostgreSQL: {e}")
                return

        cur = conn.cursor()

        try:
            if demand_file:
                # Save uploaded file to ../files/resource/
                save_path = os.path.join(resource_dir, demand_file.name)
                with open(save_path, "wb") as f:
                    f.write(demand_file.read())
                demand_file.seek(0)  # reset for parsing

                df = parse_bpafg_demand(save_path)
                n = insert_bpafg_to_db(df, cur, use_postgres=is_pg)
                st.success(f"Ingested {n} demand rows. File saved to `files/resource/`.")

            if priority_file:
                save_path = os.path.join(resource_dir, priority_file.name)
                with open(save_path, "wb") as f:
                    f.write(priority_file.read())
                priority_file.seek(0)

                df = parse_priority_template(save_path)
                n = insert_priority_to_db(df, cur, use_postgres=is_pg)
                st.success(f"Ingested {n} priority rows. File saved to `files/resource/`.")

            conn.commit()
            st.cache_data.clear()
            st.rerun()

        except Exception as e:
            st.error(f"Ingest error: {e}")
            logger.exception(e)
        finally:
            conn.close()

    def _run_ingest(self):
        """Run the parser on the ../files/resource/ folder using PostgreSQL."""
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
                st.success(f"Ingested {n} total rows from files/resource/ folder.")
                st.cache_data.clear()
            finally:
                conn.close()
        except Exception as e:
            st.error(f"Ingest error: {e}")
            logger.exception(e)
