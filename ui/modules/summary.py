import streamlit as st
import logging
import pandas as pd
import numpy as np
from sqlalchemy import text
from typing import List, Optional, Tuple

from config.config import Config
from utils.models.database import OpexDB
from .base import PageBase

# Try importing AgentUtils for LLM analysis
try:
    from agents.utils.agent_utils import AgentUtils
except ImportError:
    AgentUtils = None

logger = logging.getLogger(__name__)

class WinOpexDashboard:
    """
    Renders the high-level WIN Opex Summary Dashboard matching the executive slide format.
    Includes Full Year Summary, Quarterly Comparisons, and Project Breakdowns.
    """
    def __init__(self, df: pd.DataFrame, fiscal_year: str):
        self.df = df
        self.fiscal_year = fiscal_year

        # Determine latest and previous quarters dynamically
        if 'fiscal_quarter' in self.df.columns:
            valid_quarters = self.df['fiscal_quarter'].dropna().unique()
            quarters = sorted(valid_quarters, reverse=True)
        else:
            quarters = []
        self.latest_qtr = quarters[0] if len(quarters) > 0 else "Unknown"
        self.prev_qtr = quarters[1] if len(quarters) > 1 else None

        # Detect whether data has a 'version' column for Budget/Actual split
        self.has_version = 'version' in self.df.columns and self.df['version'].notna().any()

        # Initialize LLM Agent
        self.agent = AgentUtils() if AgentUtils else None

    def _aggregate_category(self, row):
        """Helper to map database categories to Slide categories (HW, SW, Allocations)."""
        # Prioritize explicit 'hw_sw' key if present
        val = str(row.get('hw_sw', '')).lower()
        if not val or val == 'nan':
            val = str(row.get('opex_type', '')).lower() + " " + str(row.get('cost_center', '')).lower()
        
        if 'hardware' in val or 'hw' in val:
            return 'HW'
        elif 'software' in val or 'sw' in val:
            return 'SW'
        elif 'allocation' in val or 'overhead' in val:
            return 'Allocations'
        return 'Other'

    def _get_version_type(self, version_str):
        v = str(version_str).lower()
        if 'rff' in v or 'budget' in v or 'plan' in v: return 'Budget'
        if 'act' in v: return 'Actual'
        return 'Other'

    def _prepare_variance_data(self, df_subset, value_col, group_cols):
        """Generic helper to prepare Budget vs Actual tables.

        When a 'version' column is available in the data, it is used to pivot
        into Budget vs Actual.  Otherwise, the method falls back to using
        tm1_mm as Budget and ods_mm as Actual (the standard OpEx convention).
        """
        df_subset = df_subset.copy()

        if self.has_version and value_col in df_subset.columns:
            # ── Version-based pivot ──
            df_subset['Ver_Type'] = df_subset['version'].apply(self._get_version_type)
            grouped = (
                df_subset.groupby(group_cols + ['Ver_Type'])[value_col]
                .sum()
                .unstack(fill_value=0)
                .reset_index()
            )
            if 'Budget' not in grouped.columns:
                grouped['Budget'] = 0.0
            if 'Actual' not in grouped.columns:
                grouped['Actual'] = 0.0
        else:
            # ── Fallback: tm1_mm = Budget, ods_mm = Actual ──
            has_budget = 'tm1_mm' in df_subset.columns
            has_actual = 'ods_mm' in df_subset.columns
            if not has_budget and not has_actual:
                return pd.DataFrame()

            agg_dict = {}
            if has_budget:
                df_subset['tm1_mm'] = pd.to_numeric(df_subset['tm1_mm'], errors='coerce').fillna(0)
                agg_dict['Budget'] = ('tm1_mm', 'sum')
            if has_actual:
                df_subset['ods_mm'] = pd.to_numeric(df_subset['ods_mm'], errors='coerce').fillna(0)
                agg_dict['Actual'] = ('ods_mm', 'sum')

            grouped = df_subset.groupby(group_cols).agg(**agg_dict).reset_index()
            if 'Budget' not in grouped.columns:
                grouped['Budget'] = 0.0
            if 'Actual' not in grouped.columns:
                grouped['Actual'] = 0.0

        grouped['Variance'] = grouped['Budget'] - grouped['Actual']
        grouped['Variance %'] = grouped.apply(
            lambda x: (x['Variance'] / x['Budget'] * 100) if x['Budget'] != 0 else 0, axis=1
        )
        return grouped

    def render_fy_summary(self):
        """Renders the 'Full Year WIN Opex Summary' slide (Financials & PM)."""
        st.markdown(f"## {self.fiscal_year} Full Year WIN Opex Summary")
        
        # --- Section 1: Financials ($M) ---
        col_fin, col_drivers = st.columns([1.5, 1])
        
        with col_fin:
            st.subheader("Engineering $M")
            value_col = 'ods_mm' if 'ods_mm' in self.df.columns else 'amount'
            
            # Prepare Data
            df_fin = self.df.copy()
            df_fin['Category'] = df_fin.apply(self._aggregate_category, axis=1)
            
            summary_df = self._prepare_variance_data(df_fin, value_col, ['Category'])
            
            if not summary_df.empty:
                # Custom Sort
                order_map = {'HW': 1, 'SW': 2, 'Allocations': 3}
                summary_df['sort'] = summary_df['Category'].map(order_map).fillna(4)
                summary_df = summary_df.sort_values('sort').drop('sort', axis=1)
                
                # Add Total Row
                total_bud = summary_df['Budget'].sum()
                total_act = summary_df['Actual'].sum()
                total_var = total_bud - total_act
                total_pct = (total_var / total_bud * 100) if total_bud else 0
                
                # Formatting for Display
                disp_df = summary_df.copy()
                disp_df['Budget'] = disp_df['Budget'].apply(lambda x: f"${x:,.1f}")
                disp_df['Actual'] = disp_df['Actual'].apply(lambda x: f"${x:,.1f}")
                disp_df['Variance'] = disp_df['Variance'].apply(lambda x: f"$({abs(x):.1f})" if x < 0 else f"${x:.1f}")
                disp_df['Variance %'] = disp_df['Variance %'].apply(lambda x: f"{x:.0f}%")
                
                # Append Total
                total_row = pd.DataFrame([{
                    'Category': 'Total Spend', 
                    'Budget': f"${total_bud:,.1f}", 
                    'Actual': f"${total_act:,.1f}",
                    'Variance': f"$({abs(total_var):.1f})" if total_var < 0 else f"${total_var:.1f}",
                    'Variance %': f"{total_pct:.0f}%"
                }])
                
                st.table(pd.concat([disp_df, total_row], ignore_index=True))
            else:
                st.info("No Financial Data Available")

            # --- Section 2: PM (Resource) ---
            st.subheader("Engineering PM")
            pm_col = 'tm1_mm'
            if pm_col in self.df.columns:
                df_pm = self.df.copy()
                df_pm['Category'] = df_pm.apply(self._aggregate_category, axis=1)
                
                pm_summary = self._prepare_variance_data(df_pm, pm_col, ['Category'])
                
                if not pm_summary.empty:
                    # Custom Sort
                    pm_summary['sort'] = pm_summary['Category'].map(order_map).fillna(4)
                    pm_summary = pm_summary.sort_values('sort').drop('sort', axis=1)

                    # Add Total Row
                    t_bud = pm_summary['Budget'].sum()
                    t_act = pm_summary['Actual'].sum()
                    t_var = t_bud - t_act
                    
                    # Format
                    pm_disp = pm_summary.copy()
                    pm_disp['Budget'] = pm_disp['Budget'].apply(lambda x: f"{x:,.0f}")
                    pm_disp['Actual'] = pm_disp['Actual'].apply(lambda x: f"{x:,.0f}")
                    pm_disp['Variance'] = pm_disp['Variance'].apply(lambda x: f"{x:,.0f}")
                    pm_disp['Variance %'] = pm_disp['Variance %'].apply(lambda x: f"{x:.0f}%")

                    t_row = pd.DataFrame([{
                        'Category': 'Total PM',
                        'Budget': f"{t_bud:,.0f}",
                        'Actual': f"{t_act:,.0f}",
                        'Variance': f"{t_var:,.0f}",
                        'Variance %': f"{(t_var/t_bud*100) if t_bud else 0:.0f}%"
                    }])
                    
                    st.table(pd.concat([pm_disp, t_row], ignore_index=True))
            else:
                st.info("No PM Data Available")

        # --- Section 3: Drivers Analysis (LLM) ---
        with col_drivers:
            self.render_drivers_llm()

    def render_drivers_llm(self):
        """Generates LLM-based commentary comparing Latest Q vs Previous Q and FY performance."""
        st.subheader("Key Drivers Analysis")

        if not self.agent:
            st.warning("AI Agent not available for driver analysis.")
            return

        if 'fiscal_quarter' not in self.df.columns or self.latest_qtr == "Unknown":
            st.info("No quarterly data available for AI driver analysis.")
            return

        # Prepare context data — compare Latest Q vs Prev Q
        filter_quarters = [q for q in [self.latest_qtr, self.prev_qtr] if q is not None]
        q_data = self.df[self.df['fiscal_quarter'].isin(filter_quarters)].copy()

        if q_data.empty:
            st.info("Insufficient quarterly data for analysis.")
            return

        # Aggregation for prompt
        group_cols = ['fiscal_quarter']
        if 'hw_sw' in q_data.columns:
            group_cols.append('hw_sw')
        val_col = 'ods_mm' if 'ods_mm' in q_data.columns else 'tm1_mm'
        if val_col not in q_data.columns:
            st.info("No spend data available for analysis.")
            return
        q_data[val_col] = pd.to_numeric(q_data[val_col], errors='coerce').fillna(0)
        breakdown = q_data.groupby(group_cols)[val_col].sum().reset_index()
        
        prompt = f"""
        You are a financial analyst. Analyze the following OPEX data for {self.fiscal_year}.
        
        Context:
        - Current Quarter: {self.latest_qtr}
        - Previous Quarter: {self.prev_qtr if self.prev_qtr else 'N/A'}
        
        Data Summary (Spend in $M):
        {breakdown.to_string(index=False)}
        
        Please provide a concise "Key Drivers" commentary (bullet points) explaining the financial performance.
        - Highlight major changes between {self.prev_qtr} and {self.latest_qtr}.
        - Mention if HW or SW is driving the cost.
        - Keep it executive style (brief, high-impact).
        """
        
        with st.spinner("Generating AI Analysis..."):
            try:
                response = self.agent.llm_call(prompt)
                st.markdown(response)
            except Exception as e:
                st.error(f"Analysis generation failed: {e}")

    def render_project_spend_breakdown(self):
        """Renders 'WIN Project Spend' table (Latest Quarter Breakdown)."""
        st.markdown("---")
        label = self.latest_qtr if self.latest_qtr != "Unknown" else "All Data"
        st.markdown(f"### WIN Project Spend ({label})")

        # Filter for Latest Quarter if available, otherwise use full dataset
        if 'fiscal_quarter' in self.df.columns and self.latest_qtr != "Unknown":
            df_q = self.df[self.df['fiscal_quarter'] == self.latest_qtr].copy()
        else:
            df_q = self.df.copy()

        if df_q.empty:
            st.info(f"No data for {label}")
            return

        # Define Grouping (HW/SW -> Rollup -> Project)
        # Use 'proj_rollup' if exists, else project_desc
        rollup_col = 'proj_rollup' if 'proj_rollup' in df_q.columns else 'project_desc'
        if 'project_desc' not in df_q.columns and 'additional_data' in df_q.columns:
             # Just in case json normalization didn't fully work at root
             pass 

        # Ensure HW/SW column
        df_q['Category'] = df_q.apply(self._aggregate_category, axis=1)

        # Aggregate
        # We want: Category | Rollup | Budget | Actual | Variance
        group_cols = ['Category', rollup_col]
        spend_df = self._prepare_variance_data(df_q, 'ods_mm', group_cols)
        
        if spend_df.empty:
            st.info("No spend data found.")
            return

        # Format for display
        st.dataframe(
            spend_df.style.format({
                'Budget': "${:,.2f}",
                'Actual': "${:,.2f}",
                'Variance': "${:,.2f}",
                'Variance %': "{:.1f}%"
            }),
            use_container_width=True,
            hide_index=True
        )

    def render_loe_breakdown(self):
        """Renders 'WIN Project LoE' table (Latest Quarter Breakdown)."""
        st.markdown("---")
        label = self.latest_qtr if self.latest_qtr != "Unknown" else "All Data"
        st.markdown(f"### WIN Project LoE ({label})")

        if 'fiscal_quarter' in self.df.columns and self.latest_qtr != "Unknown":
            df_q = self.df[self.df['fiscal_quarter'] == self.latest_qtr].copy()
        else:
            df_q = self.df.copy()
        if 'tm1_mm' not in df_q.columns or df_q.empty:
            st.info("No LoE (PM) data available.")
            return

        rollup_col = 'proj_rollup' if 'proj_rollup' in df_q.columns else 'project_desc'
        df_q['Category'] = df_q.apply(self._aggregate_category, axis=1)

        loe_df = self._prepare_variance_data(df_q, 'tm1_mm', ['Category', rollup_col])
        
        if loe_df.empty:
            st.info("No LoE data found.")
            return

        st.dataframe(
            loe_df.style.format({
                'Budget': "{:,.0f}",
                'Actual': "{:,.0f}",
                'Variance': "{:,.0f}",
                'Variance %': "{:.1f}%"
            }),
            use_container_width=True,
            hide_index=True
        )


class Summary(PageBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db = OpexDB
        self._projects = None  # lazy-loaded to avoid startup DB errors

    @property
    def projects(self):
        if self._projects is None:
            self._projects = self.get_available_projects()
        return self._projects

    def get_available_projects(self) -> List[str]:
        """Fetch unique project names using the confirmed key 'project_desc'."""
        try:
            query = """
            SELECT DISTINCT additional_data->>'project_desc' as project
            FROM opex_data_hybrid
            WHERE additional_data->>'project_desc' IS NOT NULL
            AND COALESCE(data_type, 'dollar') = 'dollar'
            ORDER BY 1
            """
            with self.db.engine.connect() as conn:
                result = conn.execute(text(query)).fetchall()
                return [row[0] for row in result]
        except Exception as e:
            logger.error(f"Error fetching projects: {e}")
            return []

    def get_latest_data(self, project_name: str) -> tuple[str, pd.DataFrame]:
        try:
            # 1. Fetch raw data for the project
            query = """
                SELECT *
                FROM opex_data_hybrid
                WHERE additional_data->>'project_desc' = :pname
                AND COALESCE(data_type, 'dollar') = 'dollar'
            """
            raw_df = pd.read_sql(text(query), self.db.engine, params={"pname": project_name})
            
            if raw_df.empty:
                return "Unknown", raw_df

            # 2. Unpack JSON
            if 'additional_data' in raw_df.columns:
                json_df = pd.json_normalize(raw_df['additional_data'])
                # Drop overlapping columns
                main_cols = set(raw_df.columns) - {'additional_data'}
                json_cols = set(json_df.columns)
                overlaps = main_cols.intersection(json_cols)
                if overlaps:
                    json_df = json_df.drop(columns=overlaps)
                df = pd.concat([raw_df.drop('additional_data', axis=1), json_df], axis=1)
            else:
                df = raw_df

            # 3. Coerce numeric columns (JSONB values arrive as strings)
            for num_col in ['ods_mm', 'tm1_mm']:
                if num_col in df.columns:
                    df[num_col] = pd.to_numeric(df[num_col], errors='coerce').fillna(0)

            # 4. Determine Latest Fiscal Year
            if 'fiscal_year' in df.columns:
                df['fiscal_year'] = df['fiscal_year'].astype(str)
                latest_fy = df['fiscal_year'].max()

                # 5. Filter for ONLY the latest FY (to show Full Year data)
                fy_df = df[df['fiscal_year'] == latest_fy].copy()
                return latest_fy, fy_df

            return "Unknown", df

        except Exception as e:
            logger.error(f"Error fetching data for {project_name}: {e}")
            return "Error", pd.DataFrame()

    def render(self):
        super().render()
        st.title("Executive Dashboard")

        try:
            from utils.models.database import check_opex_db
            ok, err_msg = check_opex_db()
            if not ok:
                st.warning(err_msg)
                return
        except ImportError:
            pass  # check_opex_db not available — fall through to normal flow

        if not self.projects:
            st.warning("No projects found using key 'project_desc'. Please check database.")
            return

        col_sel, _ = st.columns([1, 2])
        with col_sel:
            selected_project = st.selectbox("Select Project for Deep Dive", self.projects)

        if selected_project:
            fy, df = self.get_latest_data(selected_project)
            
            if df.empty:
                st.warning(f"No data found for {selected_project}.")
            else:
                dash = WinOpexDashboard(df, fy)
                
                # Render Sections
                dash.render_fy_summary()
                dash.render_project_spend_breakdown()
                dash.render_loe_breakdown()