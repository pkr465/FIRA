"""
FIRA What-If Scenarios — OpEx Budget Simulator + Resource Planner Cost Bridge

Provides interactive what-if analysis for OpEx budgets:
  - Budget adjustment sliders per project / category
  - Project add/remove toggles
  - Growth-rate projections (forward-looking quarters)
  - Side-by-side Base Case vs Scenario comparison
  - Cost Bridge: HC changes → dollar impact using cost multipliers
  - Save / load scenario snapshots
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import logging
import json
import copy
from typing import Dict, List, Optional, Tuple
from sqlalchemy import text

from config.config import Config
from utils.models.database import OpexDB
from .base import PageBase

logger = logging.getLogger(__name__)

# ── Fiscal month ordering ────────────────────────────────────────────────────
FISCAL_MONTH_ORDER = [
    "Oct", "Nov", "Dec", "Jan", "Feb", "Mar",
    "Apr", "May", "Jun", "Jul", "Aug", "Sep",
]

# ── Color palette ────────────────────────────────────────────────────────────
COLORS = {
    "base": "#2196F3",
    "scenario": "#FF9800",
    "positive": "#4CAF50",
    "negative": "#F44336",
    "neutral": "#9E9E9E",
    "bridge_up": "#66BB6A",
    "bridge_down": "#EF5350",
}


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=120)
def _load_opex_dollar() -> pd.DataFrame:
    """Load all dollar-type OpEx data and unpack JSONB."""
    try:
        query = text("""
            SELECT * FROM opex_data_hybrid
            WHERE COALESCE(data_type, 'dollar') = 'dollar'
        """)
        raw = pd.read_sql(query, OpexDB.engine)
        if raw.empty:
            return pd.DataFrame()

        # Unpack JSONB additional_data
        if "additional_data" in raw.columns:
            json_df = pd.json_normalize(raw["additional_data"])
            overlap = set(raw.columns) - {"additional_data"} & set(json_df.columns)
            if overlap:
                json_df = json_df.drop(columns=overlap)
            df = pd.concat([raw.drop("additional_data", axis=1), json_df], axis=1)
        else:
            df = raw

        # Coerce numerics
        for col in ["ods_m", "tm1_m"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        return df
    except Exception as e:
        logger.error(f"Error loading OpEx dollar data: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120)
def _load_opex_mm() -> pd.DataFrame:
    """Load all MM-type OpEx data and unpack JSONB."""
    try:
        query = text("""
            SELECT * FROM opex_data_hybrid
            WHERE COALESCE(data_type, 'dollar') = 'mm'
        """)
        raw = pd.read_sql(query, OpexDB.engine)
        if raw.empty:
            return pd.DataFrame()

        if "additional_data" in raw.columns:
            json_df = pd.json_normalize(raw["additional_data"])
            overlap = set(raw.columns) - {"additional_data"} & set(json_df.columns)
            if overlap:
                json_df = json_df.drop(columns=overlap)
            df = pd.concat([raw.drop("additional_data", axis=1), json_df], axis=1)
        else:
            df = raw

        for col in ["ods_mm", "tm1_mm"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        return df
    except Exception as e:
        logger.error(f"Error loading OpEx MM data: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def _load_resource_planner_costs() -> pd.DataFrame:
    """Load cost multipliers from the priority_template table."""
    try:
        from db.cbn_tables import get_pg_connection
        conn = get_pg_connection()
        df = pd.read_sql_query(
            "SELECT DISTINCT country, target_capacity, country_cost "
            "FROM priority_template WHERE country IS NOT NULL AND country_cost IS NOT NULL",
            conn,
        )
        conn.close()
        return df
    except Exception as e:
        logger.warning(f"Could not load resource planner costs: {e}")
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
# WHAT-IF ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class WhatIfEngine:
    """Applies scenario adjustments to base OpEx data and computes impacts."""

    def __init__(self, base_dollar: pd.DataFrame, base_mm: pd.DataFrame):
        self.base_dollar = base_dollar.copy()
        self.base_mm = base_mm.copy()

    # ── Project-level budget adjustment ───────────────────────────────────

    def adjust_project_budgets(
        self,
        df: pd.DataFrame,
        adjustments: Dict[str, float],
        excluded_projects: set,
    ) -> pd.DataFrame:
        """
        Apply % adjustments to ODS spend per project and exclude toggled-off projects.
        adjustments: {project_name: pct_change} e.g. {"ProjectX": 15.0} means +15%
        excluded_projects: set of project names to zero out
        """
        out = df.copy()
        proj_col = "project_desc" if "project_desc" in out.columns else None
        if proj_col is None:
            return out

        # Apply exclusions
        if excluded_projects:
            mask = out[proj_col].isin(excluded_projects)
            out.loc[mask, "ods_m"] = 0
            out.loc[mask, "tm1_m"] = 0

        # Apply % adjustments
        for proj, pct in adjustments.items():
            if pct == 0:
                continue
            mask = out[proj_col] == proj
            multiplier = 1 + (pct / 100.0)
            out.loc[mask, "ods_m"] = out.loc[mask, "ods_m"] * multiplier
            out.loc[mask, "tm1_m"] = out.loc[mask, "tm1_m"] * multiplier

        return out

    # ── Category-level growth projection ──────────────────────────────────

    def apply_growth_rate(
        self,
        df: pd.DataFrame,
        growth_pct: float,
        category_col: str = "hw_sw",
        category_filter: Optional[str] = None,
    ) -> pd.DataFrame:
        """Apply uniform growth % to spend. Optionally filter to HW or SW only."""
        out = df.copy()
        multiplier = 1 + (growth_pct / 100.0)
        if category_filter and category_col in out.columns:
            mask = out[category_col].str.lower().str.contains(category_filter.lower(), na=False)
            out.loc[mask, "ods_m"] = out.loc[mask, "ods_m"] * multiplier
        else:
            out["ods_m"] = out["ods_m"] * multiplier
        return out

    # ── Aggregation helpers ───────────────────────────────────────────────

    @staticmethod
    def aggregate_by_project(df: pd.DataFrame) -> pd.DataFrame:
        proj_col = "project_desc" if "project_desc" in df.columns else None
        if proj_col is None:
            return pd.DataFrame()
        agg = df.groupby(proj_col).agg(
            Actual=("ods_m", "sum"),
            Budget=("tm1_m", "sum"),
        ).reset_index()
        agg.columns = ["Project", "Actual", "Budget"]
        agg["Variance"] = agg["Budget"] - agg["Actual"]
        agg["Variance %"] = np.where(
            agg["Budget"] != 0,
            (agg["Variance"] / agg["Budget"]) * 100,
            0,
        )
        return agg.sort_values("Actual", ascending=False)

    @staticmethod
    def aggregate_by_category(df: pd.DataFrame) -> pd.DataFrame:
        cat_col = "hw_sw" if "hw_sw" in df.columns else None
        if cat_col is None:
            return pd.DataFrame({"Category": ["Total"], "Actual": [df["ods_m"].sum()], "Budget": [df["tm1_m"].sum()]})
        agg = df.groupby(cat_col).agg(
            Actual=("ods_m", "sum"),
            Budget=("tm1_m", "sum"),
        ).reset_index()
        agg.columns = ["Category", "Actual", "Budget"]
        agg["Variance"] = agg["Budget"] - agg["Actual"]
        return agg.sort_values("Actual", ascending=False)

    @staticmethod
    def aggregate_by_quarter(df: pd.DataFrame) -> pd.DataFrame:
        q_col = "fiscal_quarter" if "fiscal_quarter" in df.columns else None
        if q_col is None:
            return pd.DataFrame()
        agg = df.groupby(q_col).agg(
            Actual=("ods_m", "sum"),
            Budget=("tm1_m", "sum"),
        ).reset_index()
        agg.columns = ["Quarter", "Actual", "Budget"]
        agg["Variance"] = agg["Budget"] - agg["Actual"]
        return agg

    @staticmethod
    def aggregate_by_dept(df: pd.DataFrame) -> pd.DataFrame:
        dept_col = None
        for c in ["dept_vp", "dept_lead"]:
            if c in df.columns:
                dept_col = c
                break
        if dept_col is None:
            return pd.DataFrame()
        agg = df.groupby(dept_col).agg(
            Actual=("ods_m", "sum"),
            Budget=("tm1_m", "sum"),
        ).reset_index()
        agg.columns = ["Department", "Actual", "Budget"]
        agg["Variance"] = agg["Budget"] - agg["Actual"]
        return agg.sort_values("Actual", ascending=False)


# ══════════════════════════════════════════════════════════════════════════════
# COST BRIDGE: Resource Planner HC → Dollar Impact
# ══════════════════════════════════════════════════════════════════════════════

class CostBridge:
    """Translates Resource Planner HC changes into projected dollar impact."""

    def __init__(self, cost_df: pd.DataFrame, base_dollar_df: pd.DataFrame):
        self.cost_df = cost_df
        self.base_dollar_df = base_dollar_df
        # Build country → cost mapping
        self.country_costs: Dict[str, float] = {}
        self.country_capacity: Dict[str, float] = {}
        if not cost_df.empty:
            for _, row in cost_df.iterrows():
                c = row.get("country", "")
                if c:
                    self.country_costs[c] = float(row.get("country_cost", 0) or 0)
                    self.country_capacity[c] = float(row.get("target_capacity", 0) or 0)

    def compute_hc_cost_impact(
        self, hc_adjustments: Dict[str, float]
    ) -> pd.DataFrame:
        """
        Given HC adjustments per country {country: delta_hc}, compute dollar impact.
        Returns DataFrame with columns: Country, Base HC, Adjusted HC, Delta HC,
                                         Cost/HC, Base Cost, Adjusted Cost, Delta Cost
        """
        rows = []
        for country in sorted(set(list(self.country_costs.keys()) + list(hc_adjustments.keys()))):
            base_hc = self.country_capacity.get(country, 0)
            delta = hc_adjustments.get(country, 0)
            adj_hc = base_hc + delta
            cost_per = self.country_costs.get(country, 0)
            rows.append({
                "Country": country,
                "Base HC": base_hc,
                "Adjusted HC": adj_hc,
                "Delta HC": delta,
                "Cost/HC (K/mo)": cost_per,
                "Base Cost (K/mo)": base_hc * cost_per,
                "Adjusted Cost (K/mo)": adj_hc * cost_per,
                "Delta Cost (K/mo)": delta * cost_per,
            })
        return pd.DataFrame(rows)

    def annualized_impact(self, hc_adjustments: Dict[str, float]) -> float:
        """Return annualized delta cost (K) = sum of delta_hc * cost_per_hc * 12."""
        total = 0
        for country, delta in hc_adjustments.items():
            cost_per = self.country_costs.get(country, 0)
            total += delta * cost_per * 12
        return total


# ══════════════════════════════════════════════════════════════════════════════
# STREAMLIT PAGE
# ══════════════════════════════════════════════════════════════════════════════

class WhatIfScenarios(PageBase):
    """What-If Scenarios page — OpEx budget simulation + Resource Planner cost bridge."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db = OpexDB

    # ── Session state initialization ──────────────────────────────────────

    def _init_state(self):
        defaults = {
            "wi_budget_adjustments": {},       # {project: pct_change}
            "wi_excluded_projects": set(),     # toggled-off projects
            "wi_growth_pct": 0.0,              # global growth %
            "wi_growth_category": "All",       # HW / SW / All
            "wi_hc_adjustments": {},           # {country: delta_hc}
            "wi_scenarios": [],                # saved snapshots
            "wi_active_scenario": "Current",   # name
        }
        for k, v in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = v

    # ── Render ────────────────────────────────────────────────────────────

    def render(self):
        super().render()
        self._init_state()

        # Check DB
        try:
            from utils.models.database import check_opex_db
            ok, err = check_opex_db()
            if not ok:
                st.warning(err)
                return
        except ImportError:
            pass

        # Load data
        dollar_df = _load_opex_dollar()
        mm_df = _load_opex_mm()

        if dollar_df.empty:
            st.warning("No OpEx dollar data found. Please ingest data first.")
            return

        engine = WhatIfEngine(dollar_df, mm_df)

        # ── Layout: sidebar controls + main comparison ────────────────────
        st.markdown("---")

        tab_budget, tab_costbridge, tab_compare = st.tabs([
            "Budget Scenarios",
            "HC Cost Bridge",
            "Scenario Comparison",
        ])

        # ═══ TAB 1: Budget Scenarios ══════════════════════════════════════
        with tab_budget:
            self._render_budget_scenarios(dollar_df, engine)

        # ═══ TAB 2: HC Cost Bridge ═══════════════════════════════════════
        with tab_costbridge:
            self._render_cost_bridge(dollar_df)

        # ═══ TAB 3: Scenario Comparison ═══════════════════════════════════
        with tab_compare:
            self._render_scenario_comparison(dollar_df, mm_df, engine)

    # ══════════════════════════════════════════════════════════════════════
    # TAB 1: Budget Scenarios
    # ══════════════════════════════════════════════════════════════════════

    def _render_budget_scenarios(self, dollar_df: pd.DataFrame, engine: WhatIfEngine):
        st.subheader("OpEx Budget What-If")
        st.caption("Adjust project budgets, toggle projects on/off, and apply growth rates to see projected impact.")

        # ── Controls row ──────────────────────────────────────────────────
        ctrl_col1, ctrl_col2 = st.columns([1, 1])

        with ctrl_col1:
            # Growth rate
            st.markdown("**Global Growth Adjustment**")
            growth_pct = st.slider(
                "Growth rate (%)",
                min_value=-50.0, max_value=100.0,
                value=float(st.session_state.get("wi_growth_pct", 0.0)),
                step=1.0,
                key="wi_growth_slider",
                help="Positive = increase spend, Negative = cut",
            )
            st.session_state["wi_growth_pct"] = growth_pct

            cat_options = ["All"]
            if "hw_sw" in dollar_df.columns:
                cats = dollar_df["hw_sw"].dropna().unique().tolist()
                cat_options += sorted(cats)
            growth_cat = st.selectbox(
                "Apply to category",
                cat_options,
                index=0,
                key="wi_growth_cat_select",
            )
            st.session_state["wi_growth_category"] = growth_cat

        with ctrl_col2:
            # Scenario management
            st.markdown("**Scenario Management**")
            sc_cols = st.columns(3)
            with sc_cols[0]:
                scenario_name = st.text_input("Scenario name", value="Scenario 1", key="wi_sc_name")
            with sc_cols[1]:
                st.write("")  # spacer
                st.write("")
                if st.button("Save Scenario", key="wi_save_sc", type="primary"):
                    snapshot = {
                        "name": scenario_name,
                        "budget_adjustments": dict(st.session_state.get("wi_budget_adjustments", {})),
                        "excluded_projects": list(st.session_state.get("wi_excluded_projects", set())),
                        "growth_pct": st.session_state.get("wi_growth_pct", 0),
                        "growth_category": st.session_state.get("wi_growth_category", "All"),
                        "hc_adjustments": dict(st.session_state.get("wi_hc_adjustments", {})),
                    }
                    st.session_state["wi_scenarios"].append(snapshot)
                    st.success(f"Saved '{scenario_name}'")
            with sc_cols[2]:
                st.write("")
                st.write("")
                if st.button("Reset All", key="wi_reset"):
                    st.session_state["wi_budget_adjustments"] = {}
                    st.session_state["wi_excluded_projects"] = set()
                    st.session_state["wi_growth_pct"] = 0.0
                    st.session_state["wi_growth_category"] = "All"
                    st.session_state["wi_hc_adjustments"] = {}
                    st.rerun()

            # Load saved scenario
            saved = st.session_state.get("wi_scenarios", [])
            if saved:
                names = [s["name"] for s in saved]
                load_choice = st.selectbox("Load saved scenario", ["(none)"] + names, key="wi_load_choice")
                if load_choice != "(none)":
                    idx = names.index(load_choice)
                    snap = saved[idx]
                    if st.button("Load", key="wi_load_btn"):
                        st.session_state["wi_budget_adjustments"] = snap.get("budget_adjustments", {})
                        st.session_state["wi_excluded_projects"] = set(snap.get("excluded_projects", []))
                        st.session_state["wi_growth_pct"] = snap.get("growth_pct", 0)
                        st.session_state["wi_growth_category"] = snap.get("growth_category", "All")
                        st.session_state["wi_hc_adjustments"] = snap.get("hc_adjustments", {})
                        st.success(f"Loaded '{load_choice}'")
                        st.rerun()

        st.markdown("---")

        # ── Project-level adjustments ─────────────────────────────────────
        st.markdown("**Per-Project Budget Adjustments**")

        proj_col = "project_desc" if "project_desc" in dollar_df.columns else None
        if proj_col:
            projects = sorted(dollar_df[proj_col].dropna().unique().tolist())
        else:
            projects = []

        adjustments = dict(st.session_state.get("wi_budget_adjustments", {}))
        excluded = set(st.session_state.get("wi_excluded_projects", set()))

        # Display projects in a compact table-like layout
        with st.expander(f"Adjust {len(projects)} projects", expanded=True):
            # Quick actions
            qa_cols = st.columns(4)
            with qa_cols[0]:
                if st.button("Select All", key="wi_sel_all"):
                    excluded.clear()
                    st.session_state["wi_excluded_projects"] = excluded
                    st.rerun()
            with qa_cols[1]:
                if st.button("Deselect All", key="wi_desel_all"):
                    excluded = set(projects)
                    st.session_state["wi_excluded_projects"] = excluded
                    st.rerun()
            with qa_cols[2]:
                bulk_adj = st.number_input("Bulk adjust %", value=0.0, step=5.0, key="wi_bulk_adj")
            with qa_cols[3]:
                st.write("")
                st.write("")
                if st.button("Apply to All", key="wi_apply_bulk"):
                    for p in projects:
                        adjustments[p] = bulk_adj
                    st.session_state["wi_budget_adjustments"] = adjustments
                    st.rerun()

            # Per-project rows
            base_agg = engine.aggregate_by_project(dollar_df)
            if not base_agg.empty:
                for _, row in base_agg.iterrows():
                    proj = row["Project"]
                    cols = st.columns([3, 2, 2, 1])
                    with cols[0]:
                        is_active = proj not in excluded
                        toggled = st.checkbox(
                            f"{proj}",
                            value=is_active,
                            key=f"wi_proj_{proj}",
                        )
                        if toggled and proj in excluded:
                            excluded.discard(proj)
                        elif not toggled and proj not in excluded:
                            excluded.add(proj)

                    with cols[1]:
                        st.caption(f"Base: ${row['Actual']:,.1f}M")

                    with cols[2]:
                        adj_val = st.number_input(
                            "Adjust %",
                            value=float(adjustments.get(proj, 0)),
                            step=5.0,
                            min_value=-100.0,
                            max_value=500.0,
                            key=f"wi_adj_{proj}",
                            label_visibility="collapsed",
                        )
                        adjustments[proj] = adj_val

                    with cols[3]:
                        adjusted_spend = row["Actual"] * (1 + adj_val / 100.0)
                        delta = adjusted_spend - row["Actual"]
                        color = COLORS["positive"] if delta <= 0 else COLORS["negative"]
                        st.markdown(
                            f"<span style='color:{color};font-weight:bold'>"
                            f"{'+'if delta>0 else ''}{delta:,.1f}M</span>",
                            unsafe_allow_html=True,
                        )

                st.session_state["wi_budget_adjustments"] = adjustments
                st.session_state["wi_excluded_projects"] = excluded

        # ── Apply all adjustments and show results ────────────────────────
        st.markdown("---")
        st.subheader("Scenario Impact")

        # Build scenario dataframe
        scenario_df = engine.adjust_project_budgets(dollar_df, adjustments, excluded)
        cat_filter = None if growth_cat == "All" else growth_cat
        scenario_df = engine.apply_growth_rate(scenario_df, growth_pct, category_filter=cat_filter)

        # Side-by-side KPIs
        base_total_actual = dollar_df["ods_m"].sum()
        base_total_budget = dollar_df["tm1_m"].sum()
        scen_total_actual = scenario_df["ods_m"].sum()
        scen_total_budget = scenario_df["tm1_m"].sum()

        kpi_cols = st.columns(4)
        with kpi_cols[0]:
            st.metric("Base Actual ($M)", f"${base_total_actual:,.1f}")
        with kpi_cols[1]:
            delta_actual = scen_total_actual - base_total_actual
            st.metric(
                "Scenario Actual ($M)",
                f"${scen_total_actual:,.1f}",
                delta=f"{delta_actual:+,.1f}M",
                delta_color="inverse",
            )
        with kpi_cols[2]:
            st.metric("Base Budget ($M)", f"${base_total_budget:,.1f}")
        with kpi_cols[3]:
            scen_variance = scen_total_budget - scen_total_actual
            st.metric(
                "Scenario Variance ($M)",
                f"${scen_variance:,.1f}",
                delta=f"{'Favorable' if scen_variance >= 0 else 'Unfavorable'}",
                delta_color="normal" if scen_variance >= 0 else "inverse",
            )

        # ── Comparison charts ─────────────────────────────────────────────
        ch_cols = st.columns(2)

        with ch_cols[0]:
            st.markdown("**By Project: Base vs Scenario**")
            base_proj = engine.aggregate_by_project(dollar_df)
            scen_proj = engine.aggregate_by_project(scenario_df)
            if not base_proj.empty and not scen_proj.empty:
                merged = base_proj[["Project", "Actual"]].merge(
                    scen_proj[["Project", "Actual"]],
                    on="Project", how="outer", suffixes=("_Base", "_Scenario"),
                ).fillna(0).sort_values("Actual_Base", ascending=True).tail(15)

                fig = go.Figure()
                fig.add_trace(go.Bar(
                    y=merged["Project"], x=merged["Actual_Base"],
                    name="Base", orientation="h",
                    marker_color=COLORS["base"],
                ))
                fig.add_trace(go.Bar(
                    y=merged["Project"], x=merged["Actual_Scenario"],
                    name="Scenario", orientation="h",
                    marker_color=COLORS["scenario"],
                ))
                fig.update_layout(
                    barmode="group", height=max(400, len(merged) * 28),
                    margin=dict(l=10, r=10, t=10, b=10),
                    legend=dict(orientation="h", y=1.02),
                )
                st.plotly_chart(fig, use_container_width=True, key="wi_proj_chart")

        with ch_cols[1]:
            st.markdown("**By Category: Base vs Scenario**")
            base_cat = engine.aggregate_by_category(dollar_df)
            scen_cat = engine.aggregate_by_category(scenario_df)
            if not base_cat.empty and not scen_cat.empty:
                merged_cat = base_cat[["Category", "Actual"]].merge(
                    scen_cat[["Category", "Actual"]],
                    on="Category", how="outer", suffixes=("_Base", "_Scenario"),
                ).fillna(0)

                fig2 = go.Figure()
                fig2.add_trace(go.Bar(
                    x=merged_cat["Category"], y=merged_cat["Actual_Base"],
                    name="Base", marker_color=COLORS["base"],
                ))
                fig2.add_trace(go.Bar(
                    x=merged_cat["Category"], y=merged_cat["Actual_Scenario"],
                    name="Scenario", marker_color=COLORS["scenario"],
                ))
                fig2.update_layout(
                    barmode="group", height=350,
                    margin=dict(l=10, r=10, t=10, b=10),
                    legend=dict(orientation="h", y=1.02),
                    yaxis_title="$M",
                )
                st.plotly_chart(fig2, use_container_width=True, key="wi_cat_chart")

        # ── Waterfall: Delta by Project ───────────────────────────────────
        st.markdown("**Waterfall: Spend Change by Project**")
        if not base_proj.empty and not scen_proj.empty:
            waterfall = base_proj[["Project", "Actual"]].merge(
                scen_proj[["Project", "Actual"]],
                on="Project", how="outer", suffixes=("_Base", "_Scenario"),
            ).fillna(0)
            waterfall["Delta"] = waterfall["Actual_Scenario"] - waterfall["Actual_Base"]
            waterfall = waterfall[waterfall["Delta"].abs() > 0.001].sort_values("Delta")

            if not waterfall.empty:
                colors = [COLORS["bridge_down"] if d < 0 else COLORS["bridge_up"] for d in waterfall["Delta"]]
                fig3 = go.Figure(go.Bar(
                    x=waterfall["Project"],
                    y=waterfall["Delta"],
                    marker_color=colors,
                    text=[f"{d:+,.1f}M" for d in waterfall["Delta"]],
                    textposition="outside",
                ))
                fig3.update_layout(
                    height=350, yaxis_title="Delta $M",
                    margin=dict(l=10, r=10, t=10, b=10),
                )
                st.plotly_chart(fig3, use_container_width=True, key="wi_waterfall")
            else:
                st.info("No changes to display. Adjust project budgets above.")

        # ── Data table ────────────────────────────────────────────────────
        with st.expander("Detailed Scenario Data"):
            if not base_proj.empty and not scen_proj.empty:
                detail = base_proj[["Project", "Actual", "Budget"]].merge(
                    scen_proj[["Project", "Actual", "Budget"]],
                    on="Project", how="outer", suffixes=("_Base", "_Scenario"),
                ).fillna(0)
                detail["Delta Actual"] = detail["Actual_Scenario"] - detail["Actual_Base"]
                detail["Delta %"] = np.where(
                    detail["Actual_Base"] != 0,
                    (detail["Delta Actual"] / detail["Actual_Base"]) * 100,
                    0,
                )
                # Add totals row
                totals = pd.DataFrame([{
                    "Project": "TOTAL",
                    "Actual_Base": detail["Actual_Base"].sum(),
                    "Budget_Base": detail["Budget_Base"].sum(),
                    "Actual_Scenario": detail["Actual_Scenario"].sum(),
                    "Budget_Scenario": detail["Budget_Scenario"].sum(),
                    "Delta Actual": detail["Delta Actual"].sum(),
                    "Delta %": 0,
                }])
                if totals["Actual_Base"].iloc[0] != 0:
                    totals["Delta %"] = (totals["Delta Actual"] / totals["Actual_Base"]) * 100
                detail = pd.concat([detail, totals], ignore_index=True)
                st.dataframe(
                    detail.style.format({
                        "Actual_Base": "${:,.2f}M",
                        "Budget_Base": "${:,.2f}M",
                        "Actual_Scenario": "${:,.2f}M",
                        "Budget_Scenario": "${:,.2f}M",
                        "Delta Actual": "${:+,.2f}M",
                        "Delta %": "{:+,.1f}%",
                    }),
                    use_container_width=True,
                    height=min(600, 40 + len(detail) * 35),
                )

    # ══════════════════════════════════════════════════════════════════════
    # TAB 2: HC Cost Bridge
    # ══════════════════════════════════════════════════════════════════════

    def _render_cost_bridge(self, dollar_df: pd.DataFrame):
        st.subheader("HC → Cost Bridge")
        st.caption(
            "Adjust headcount by country to see projected dollar impact. "
            "Cost multipliers come from the Resource Planner priority template."
        )

        cost_df = _load_resource_planner_costs()

        if cost_df.empty:
            st.warning(
                "No cost data found in priority_template. "
                "Upload a priority template CSV via the Resource Planner to enable cost bridge."
            )
            # Allow manual entry
            st.markdown("**Manual Cost Entry**")
            manual_countries = st.text_input(
                "Enter countries (comma separated)",
                value="India, Israel, USA",
                key="wi_manual_countries",
            )
            countries = [c.strip() for c in manual_countries.split(",") if c.strip()]
            manual_costs = {}
            manual_caps = {}
            mc_cols = st.columns(min(len(countries), 4))
            for i, country in enumerate(countries):
                with mc_cols[i % len(mc_cols)]:
                    manual_caps[country] = st.number_input(
                        f"{country} Base HC", value=50.0, step=5.0, key=f"wi_mcap_{country}",
                    )
                    manual_costs[country] = st.number_input(
                        f"{country} Cost/HC (K/mo)", value=10.0, step=1.0, key=f"wi_mcost_{country}",
                    )
            cost_df = pd.DataFrame([
                {"country": c, "target_capacity": manual_caps[c], "country_cost": manual_costs[c]}
                for c in countries
            ])

        bridge = CostBridge(cost_df, dollar_df)
        countries = sorted(bridge.country_costs.keys())

        if not countries:
            st.info("No countries with cost data available.")
            return

        # HC adjustment inputs
        st.markdown("**Headcount Adjustments by Country**")
        hc_adj = dict(st.session_state.get("wi_hc_adjustments", {}))

        adj_cols = st.columns(min(len(countries), 4))
        for i, country in enumerate(countries):
            with adj_cols[i % len(adj_cols)]:
                base_hc = bridge.country_capacity.get(country, 0)
                st.caption(f"{country} (Base: {base_hc:.0f} HC)")
                delta = st.number_input(
                    f"Delta HC",
                    value=float(hc_adj.get(country, 0)),
                    step=5.0,
                    key=f"wi_hc_{country}",
                    label_visibility="collapsed",
                )
                hc_adj[country] = delta

        st.session_state["wi_hc_adjustments"] = hc_adj

        # Compute impact
        impact_df = bridge.compute_hc_cost_impact(hc_adj)
        annual = bridge.annualized_impact(hc_adj)

        # KPIs
        st.markdown("---")
        kpi_cols = st.columns(4)
        total_base_cost = impact_df["Base Cost (K/mo)"].sum()
        total_adj_cost = impact_df["Adjusted Cost (K/mo)"].sum()
        total_delta = impact_df["Delta Cost (K/mo)"].sum()

        with kpi_cols[0]:
            st.metric("Base Monthly Cost", f"${total_base_cost:,.0f}K")
        with kpi_cols[1]:
            st.metric(
                "Adjusted Monthly Cost", f"${total_adj_cost:,.0f}K",
                delta=f"{total_delta:+,.0f}K/mo",
                delta_color="inverse",
            )
        with kpi_cols[2]:
            st.metric(
                "Annualized Impact", f"${annual:+,.0f}K/yr",
                delta=f"${annual / 1000:+,.1f}M/yr",
                delta_color="inverse",
            )
        with kpi_cols[3]:
            total_base_hc = impact_df["Base HC"].sum()
            total_adj_hc = impact_df["Adjusted HC"].sum()
            st.metric(
                "Total HC",
                f"{total_adj_hc:,.0f}",
                delta=f"{total_adj_hc - total_base_hc:+,.0f}",
                delta_color="normal",
            )

        # Impact table
        st.markdown("**Cost Impact by Country**")
        st.dataframe(
            impact_df.style.format({
                "Base HC": "{:,.1f}",
                "Adjusted HC": "{:,.1f}",
                "Delta HC": "{:+,.1f}",
                "Cost/HC (K/mo)": "${:,.1f}",
                "Base Cost (K/mo)": "${:,.0f}",
                "Adjusted Cost (K/mo)": "${:,.0f}",
                "Delta Cost (K/mo)": "${:+,.0f}",
            }),
            use_container_width=True,
            hide_index=True,
        )

        # Bar chart: base vs adjusted cost by country
        st.markdown("**Monthly Cost: Base vs Adjusted**")
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=impact_df["Country"], y=impact_df["Base Cost (K/mo)"],
            name="Base Cost", marker_color=COLORS["base"],
        ))
        fig.add_trace(go.Bar(
            x=impact_df["Country"], y=impact_df["Adjusted Cost (K/mo)"],
            name="Adjusted Cost", marker_color=COLORS["scenario"],
        ))
        fig.update_layout(
            barmode="group", height=350, yaxis_title="K/month",
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True, key="wi_cost_bridge_chart")

        # Waterfall: delta cost by country
        if impact_df["Delta Cost (K/mo)"].abs().sum() > 0:
            st.markdown("**Cost Delta Waterfall**")
            deltas = impact_df[impact_df["Delta Cost (K/mo)"].abs() > 0].copy()
            colors = [COLORS["bridge_down"] if d < 0 else COLORS["bridge_up"]
                      for d in deltas["Delta Cost (K/mo)"]]

            fig_w = go.Figure(go.Waterfall(
                x=deltas["Country"].tolist() + ["Total"],
                y=deltas["Delta Cost (K/mo)"].tolist() + [total_delta],
                measure=["relative"] * len(deltas) + ["total"],
                connector={"line": {"color": "rgba(0,0,0,0)"}},
                increasing={"marker": {"color": COLORS["bridge_up"]}},
                decreasing={"marker": {"color": COLORS["bridge_down"]}},
                totals={"marker": {"color": COLORS["base"]}},
                text=[f"{d:+,.0f}K" for d in deltas["Delta Cost (K/mo)"]] + [f"{total_delta:+,.0f}K"],
                textposition="outside",
            ))
            fig_w.update_layout(
                height=350, yaxis_title="Delta K/month",
                margin=dict(l=10, r=10, t=30, b=10),
            )
            st.plotly_chart(fig_w, use_container_width=True, key="wi_cost_waterfall")

    # ══════════════════════════════════════════════════════════════════════
    # TAB 3: Scenario Comparison
    # ══════════════════════════════════════════════════════════════════════

    def _render_scenario_comparison(self, dollar_df, mm_df, engine):
        st.subheader("Scenario Comparison")
        st.caption("Compare saved scenarios side by side.")

        saved = st.session_state.get("wi_scenarios", [])
        if not saved:
            st.info(
                "No saved scenarios yet. Go to 'Budget Scenarios' tab, make adjustments, "
                "and click 'Save Scenario' to create scenarios for comparison."
            )
            return

        # Let user pick scenarios to compare
        names = [s["name"] for s in saved]
        selected = st.multiselect(
            "Select scenarios to compare",
            names,
            default=names[:min(3, len(names))],
            key="wi_compare_select",
        )

        if len(selected) < 1:
            st.info("Select at least one scenario to compare.")
            return

        # Build comparison table
        rows = []
        scenario_dfs = {}

        # Always include base case
        base_total = dollar_df["ods_m"].sum()
        base_budget = dollar_df["tm1_m"].sum()
        rows.append({
            "Scenario": "Base Case",
            "Total Actual ($M)": base_total,
            "Total Budget ($M)": base_budget,
            "Variance ($M)": base_budget - base_total,
            "Active Projects": len(dollar_df["project_desc"].dropna().unique()) if "project_desc" in dollar_df.columns else 0,
            "Growth %": 0,
        })

        for name in selected:
            idx = names.index(name)
            snap = saved[idx]
            # Replay scenario
            adj = snap.get("budget_adjustments", {})
            excl = set(snap.get("excluded_projects", []))
            gpct = snap.get("growth_pct", 0)
            gcat = snap.get("growth_category", "All")

            sdf = engine.adjust_project_budgets(dollar_df, adj, excl)
            cat_filter = None if gcat == "All" else gcat
            sdf = engine.apply_growth_rate(sdf, gpct, category_filter=cat_filter)
            scenario_dfs[name] = sdf

            s_total = sdf["ods_m"].sum()
            s_budget = sdf["tm1_m"].sum()
            active = 0
            if "project_desc" in sdf.columns:
                active_df = sdf[sdf["ods_m"] > 0]
                active = len(active_df["project_desc"].dropna().unique())

            rows.append({
                "Scenario": name,
                "Total Actual ($M)": s_total,
                "Total Budget ($M)": s_budget,
                "Variance ($M)": s_budget - s_total,
                "Active Projects": active,
                "Growth %": gpct,
            })

        comp_df = pd.DataFrame(rows)
        st.dataframe(
            comp_df.style.format({
                "Total Actual ($M)": "${:,.1f}",
                "Total Budget ($M)": "${:,.1f}",
                "Variance ($M)": "${:+,.1f}",
                "Growth %": "{:+,.1f}%",
            }),
            use_container_width=True,
            hide_index=True,
        )

        # Bar chart comparison
        st.markdown("**Total Spend Comparison**")
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=comp_df["Scenario"], y=comp_df["Total Actual ($M)"],
            name="Actual", marker_color=COLORS["scenario"],
        ))
        fig.add_trace(go.Bar(
            x=comp_df["Scenario"], y=comp_df["Total Budget ($M)"],
            name="Budget", marker_color=COLORS["base"],
        ))
        fig.update_layout(
            barmode="group", height=350, yaxis_title="$M",
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True, key="wi_compare_chart")

        # Per-scenario project breakdown
        if len(selected) >= 1:
            st.markdown("**Project-Level Comparison**")
            base_proj = engine.aggregate_by_project(dollar_df)
            if not base_proj.empty:
                comparison = base_proj[["Project", "Actual"]].rename(columns={"Actual": "Base Case"})
                for name in selected:
                    sdf = scenario_dfs.get(name)
                    if sdf is not None:
                        sp = engine.aggregate_by_project(sdf)
                        if not sp.empty:
                            comparison = comparison.merge(
                                sp[["Project", "Actual"]].rename(columns={"Actual": name}),
                                on="Project", how="outer",
                            )
                comparison = comparison.fillna(0)
                # Add delta columns
                for name in selected:
                    if name in comparison.columns:
                        comparison[f"Δ {name}"] = comparison[name] - comparison["Base Case"]

                st.dataframe(
                    comparison.style.format(
                        {col: "${:,.2f}M" for col in comparison.columns if col != "Project"}
                    ),
                    use_container_width=True,
                    height=min(600, 40 + len(comparison) * 35),
                )

        # Download
        csv_data = comp_df.to_csv(index=False)
        st.download_button(
            "Download Comparison CSV",
            csv_data,
            file_name="whatif_scenario_comparison.csv",
            mime="text/csv",
            key="wi_download_csv",
        )
