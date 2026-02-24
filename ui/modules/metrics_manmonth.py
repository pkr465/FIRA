"""
Man-Month Analysis Dashboard

Displays resource estimates (man-months) from the MM Data sheet.
Uses ODS_MM as the primary man-month metric across all projects.
Provides breakdowns by project, department, HW/SW, expense type,
and monthly/quarterly trends.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import text
from typing import List

from utils.models.database import OpexDB
from .base import PageBase


class ManMonthDashboard:
    """Renders man-month analytics from MM Data."""

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

        # Coerce key numeric columns
        for col in ['ods_mm', 'tm1_mm']:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce').fillna(0)

        # Sort months fiscally (Oct start)
        self.month_order = ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar',
                            'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep']
        if 'fiscal_month' in self.df.columns:
            self.df['fiscal_month'] = pd.Categorical(
                self.df['fiscal_month'], categories=self.month_order, ordered=True
            )
            self.df = self.df.sort_values('fiscal_month')

    def render(self):
        has_ods = 'ods_mm' in self.df.columns
        has_tm1 = 'tm1_mm' in self.df.columns
        has_month = 'fiscal_month' in self.df.columns
        has_quarter = 'fiscal_quarter' in self.df.columns and self.df['fiscal_quarter'].notna().any()
        has_hw_sw = 'hw_sw' in self.df.columns and self.df['hw_sw'].notna().any()

        if not has_ods:
            st.info("No man-month data available (ods_mm column missing).")
            return

        # ── Summary KPIs ──
        total_ods = self.df['ods_mm'].sum()
        total_tm1 = self.df['tm1_mm'].sum() if has_tm1 else 0
        variance = total_tm1 - total_ods

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total ODS MM (Actual)", f"{total_ods:,.1f}")
        m2.metric("Total TM1 MM (Plan)", f"{total_tm1:,.1f}")
        m3.metric("Variance (Plan - Actual)", f"{variance:,.1f}",
                  delta=f"{variance:,.1f}", delta_color="normal")
        unique_projects = self.df['project_desc'].nunique() if 'project_desc' in self.df.columns else '—'
        m4.metric("Projects", unique_projects)

        st.markdown("---")

        # ── 1. Monthly Man-Month Trend ──
        if has_month:
            st.subheader("Monthly Man-Month Trend")

            monthly = self.df.groupby('fiscal_month').agg(
                ODS_MM=('ods_mm', 'sum'),
                TM1_MM=('tm1_mm', 'sum') if has_tm1 else ('ods_mm', 'sum'),
            ).reset_index()

            fig_trend = go.Figure()
            fig_trend.add_trace(go.Bar(
                x=monthly['fiscal_month'], y=monthly['TM1_MM'],
                name='Plan (TM1 MM)', marker_color='#1f77b4',
            ))
            fig_trend.add_trace(go.Bar(
                x=monthly['fiscal_month'], y=monthly['ODS_MM'],
                name='Actual (ODS MM)', marker_color='#2ca02c',
            ))
            fig_trend.add_trace(go.Scatter(
                x=monthly['fiscal_month'],
                y=monthly['TM1_MM'] - monthly['ODS_MM'],
                name='Variance', mode='lines+markers',
                line=dict(color='#d62728', dash='dash'),
            ))
            fig_trend.update_layout(
                barmode='group',
                xaxis_title="Fiscal Month",
                yaxis_title="Man-Months",
                hovermode="x unified",
            )
            st.plotly_chart(fig_trend, use_container_width=True)

        # ── 2. Quarterly Summary ──
        if has_quarter:
            st.markdown("---")
            st.subheader("Quarterly Man-Month Summary")

            q_data = self.df.groupby('fiscal_quarter').agg(
                ODS_MM=('ods_mm', 'sum'),
                TM1_MM=('tm1_mm', 'sum') if has_tm1 else ('ods_mm', 'sum'),
            ).reset_index()
            q_data['Variance'] = q_data['TM1_MM'] - q_data['ODS_MM']

            fig_q = go.Figure()
            fig_q.add_trace(go.Bar(
                x=q_data['fiscal_quarter'], y=q_data['TM1_MM'],
                name='Plan (TM1 MM)', marker_color='#1f77b4',
                text=q_data['TM1_MM'].apply(lambda x: f"{x:.1f}"),
                textposition='auto',
            ))
            fig_q.add_trace(go.Bar(
                x=q_data['fiscal_quarter'], y=q_data['ODS_MM'],
                name='Actual (ODS MM)', marker_color='#2ca02c',
                text=q_data['ODS_MM'].apply(lambda x: f"{x:.1f}"),
                textposition='auto',
            ))
            fig_q.update_layout(
                barmode='group',
                xaxis_title="Fiscal Quarter",
                yaxis_title="Man-Months",
            )
            st.plotly_chart(fig_q, use_container_width=True)

            with st.expander("View Quarterly Data"):
                q_data['Util %'] = q_data.apply(
                    lambda r: (r['ODS_MM'] / r['TM1_MM'] * 100) if r['TM1_MM'] != 0 else 0, axis=1
                )
                st.dataframe(q_data.style.format({
                    'ODS_MM': '{:,.1f}', 'TM1_MM': '{:,.1f}',
                    'Variance': '{:,.1f}', 'Util %': '{:.1f}%'
                }))

        # ── 3. Man-Months by HW/SW ──
        if has_hw_sw:
            st.markdown("---")
            st.subheader("Man-Months by HW / SW")

            hw_data = self.df.groupby('hw_sw')['ods_mm'].sum().reset_index()

            col1, col2 = st.columns(2)
            with col1:
                fig_pie = go.Figure(data=[go.Pie(
                    labels=hw_data['hw_sw'], values=hw_data['ods_mm'],
                    hole=.3, textinfo='label+percent',
                )])
                fig_pie.update_layout(title="ODS MM Distribution")
                st.plotly_chart(fig_pie, use_container_width=True)

            with col2:
                if has_month:
                    hw_trend = self.df.groupby(['fiscal_month', 'hw_sw'])['ods_mm'].sum().reset_index()
                    fig_hw = go.Figure()
                    for cat in hw_trend['hw_sw'].unique():
                        subset = hw_trend[hw_trend['hw_sw'] == cat]
                        fig_hw.add_trace(go.Scatter(
                            x=subset['fiscal_month'], y=subset['ods_mm'],
                            mode='lines+markers', name=str(cat),
                        ))
                    fig_hw.update_layout(
                        title="Monthly MM by HW/SW",
                        xaxis_title="Fiscal Month", yaxis_title="Man-Months",
                    )
                    st.plotly_chart(fig_hw, use_container_width=True)

        # ── 4. Man-Months by Expense Type ──
        exp_col = None
        for candidate in ['exp_type_r5', 'exp_type_r3']:
            if candidate in self.df.columns and self.df[candidate].notna().any():
                exp_col = candidate
                break

        if exp_col:
            st.markdown("---")
            st.subheader(f"Man-Months by Expense Type ({exp_col})")

            exp_data = self.df.groupby(exp_col)['ods_mm'].sum().sort_values(ascending=True).reset_index()
            exp_data = exp_data[exp_data['ods_mm'].abs() > 0.01]

            fig_exp = go.Figure(go.Bar(
                x=exp_data['ods_mm'], y=exp_data[exp_col],
                orientation='h',
                text=exp_data['ods_mm'].apply(lambda x: f"{x:,.1f}"),
                textposition='auto',
                marker_color=['#2ca02c' if v >= 0 else '#d62728' for v in exp_data['ods_mm']],
            ))
            fig_exp.update_layout(
                xaxis_title="Man-Months (ODS MM)",
                height=max(300, len(exp_data) * 30),
                margin=dict(l=20, r=20, t=20, b=20),
            )
            st.plotly_chart(fig_exp, use_container_width=True)

        # ── 5. Man-Months by Department Lead ──
        if 'dept_lead' in self.df.columns and self.df['dept_lead'].notna().any():
            st.markdown("---")
            st.subheader("Man-Months by Department Lead")

            lead_data = self.df.groupby('dept_lead')['ods_mm'].sum().sort_values(ascending=True).reset_index()
            lead_data = lead_data[lead_data['ods_mm'].abs() > 0.01]

            if not lead_data.empty:
                fig_lead = go.Figure(go.Bar(
                    x=lead_data['ods_mm'], y=lead_data['dept_lead'],
                    orientation='h',
                    text=lead_data['ods_mm'].apply(lambda x: f"{x:,.1f}"),
                    textposition='auto',
                    marker_color='#636EFA',
                ))
                fig_lead.update_layout(
                    xaxis_title="Man-Months (ODS MM)",
                    height=max(300, len(lead_data) * 30),
                    margin=dict(l=20, r=20, t=20, b=20),
                )
                st.plotly_chart(fig_lead, use_container_width=True)

        # ── 6. Detailed Project Breakdown ──
        if 'project_desc' in self.df.columns and self.df['project_desc'].notna().any():
            st.markdown("---")
            st.subheader("Man-Months by Project")

            proj_data = self.df.groupby('project_desc').agg(
                ODS_MM=('ods_mm', 'sum'),
                TM1_MM=('tm1_mm', 'sum') if has_tm1 else ('ods_mm', 'sum'),
            ).reset_index()
            proj_data['Variance'] = proj_data['TM1_MM'] - proj_data['ODS_MM']
            proj_data['Util %'] = proj_data.apply(
                lambda r: (r['ODS_MM'] / r['TM1_MM'] * 100) if r['TM1_MM'] != 0 else 0, axis=1
            )
            proj_data = proj_data.sort_values('ODS_MM', ascending=False)

            fig_proj = go.Figure()
            fig_proj.add_trace(go.Bar(
                x=proj_data['project_desc'], y=proj_data['TM1_MM'],
                name='Plan (TM1)', marker_color='#1f77b4',
            ))
            fig_proj.add_trace(go.Bar(
                x=proj_data['project_desc'], y=proj_data['ODS_MM'],
                name='Actual (ODS)', marker_color='#2ca02c',
            ))
            fig_proj.update_layout(
                barmode='group',
                xaxis_title="Project",
                yaxis_title="Man-Months",
                xaxis_tickangle=-45,
                height=500,
            )
            st.plotly_chart(fig_proj, use_container_width=True)

            with st.expander("View Project Data Table"):
                st.dataframe(proj_data.style.format({
                    'ODS_MM': '{:,.1f}', 'TM1_MM': '{:,.1f}',
                    'Variance': '{:,.1f}', 'Util %': '{:.1f}%'
                }), use_container_width=True)


class ManMonthAnalysis(PageBase):
    """Streamlit page for Man-Month analysis (MM Data sheet)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db = OpexDB
        self._projects = None

    @property
    def projects(self):
        if self._projects is None:
            self._projects = self.get_available_projects()
        return self._projects

    def get_available_projects(self) -> List[str]:
        try:
            query = ("SELECT DISTINCT additional_data->>'project_desc' as project "
                     "FROM opex_data_hybrid "
                     "WHERE additional_data->>'project_desc' IS NOT NULL "
                     "AND COALESCE(data_type, 'dollar') = 'mm' ORDER BY 1")
            with self.db.engine.connect() as conn:
                return [row[0] for row in conn.execute(text(query)).fetchall()]
        except Exception:
            return []

    def get_data(self, project_name: str) -> pd.DataFrame:
        query = ("SELECT * FROM opex_data_hybrid "
                 "WHERE additional_data->>'project_desc' = :pname "
                 "AND COALESCE(data_type, 'dollar') = 'mm'")
        raw_df = pd.read_sql(text(query), self.db.engine, params={"pname": project_name})

        if not raw_df.empty and 'additional_data' in raw_df.columns:
            json_df = pd.json_normalize(raw_df['additional_data'])
            cols_to_use = json_df.columns.difference(raw_df.columns)
            return pd.concat([raw_df, json_df[cols_to_use]], axis=1)
        return raw_df

    def get_all_mm_data(self) -> pd.DataFrame:
        """Fetch ALL man-month data across all projects for the overview."""
        query = ("SELECT * FROM opex_data_hybrid "
                 "WHERE COALESCE(data_type, 'dollar') = 'mm'")
        raw_df = pd.read_sql(text(query), self.db.engine)

        if not raw_df.empty and 'additional_data' in raw_df.columns:
            json_df = pd.json_normalize(raw_df['additional_data'])
            cols_to_use = json_df.columns.difference(raw_df.columns)
            return pd.concat([raw_df, json_df[cols_to_use]], axis=1)
        return raw_df

    def render(self):
        super().render()
        st.title("Man-Month Analysis")
        st.caption("Resource estimates from the MM Data sheet. ODS MM = Actual man-months, TM1 MM = Planned man-months.")

        try:
            from utils.models.database import check_opex_db
            ok, err_msg = check_opex_db()
            if not ok:
                st.warning(err_msg)
                return
        except ImportError:
            pass

        # View mode: All Projects or Single Project
        view_mode = st.radio(
            "View", ["All Projects", "Single Project"],
            horizontal=True, key="mm_view_mode",
        )

        if view_mode == "All Projects":
            df = self.get_all_mm_data()
            if df.empty:
                st.warning("No man-month data found. Ingest an Excel file with an 'MM Data' sheet.")
                return
            ManMonthDashboard(df).render()
        else:
            if not self.projects:
                st.warning("No projects with man-month data found.")
                return

            col1, _ = st.columns([1, 2])
            with col1:
                sel_proj = st.selectbox("Select Project", self.projects)

            if sel_proj:
                df = self.get_data(sel_proj)
                if not df.empty:
                    ManMonthDashboard(df).render()
                else:
                    st.warning("No man-month data for selected project.")
