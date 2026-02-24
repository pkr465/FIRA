import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import text
from typing import List

from utils.models.database import OpexDB
from .base import PageBase


class FinancialTrendsDashboard:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

        # Coerce key numeric columns (JSONB values may arrive as strings)
        for col in ['ods_m', 'tm1_m']:
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
        # ── Monthly Spend Trend ──
        st.subheader("Monthly Spend Trend ($M)")

        has_month = 'fiscal_month' in self.df.columns
        has_spend = 'ods_m' in self.df.columns
        has_hw_sw = 'hw_sw' in self.df.columns and self.df['hw_sw'].notna().any()

        if has_month and has_spend:
            if has_hw_sw:
                monthly = self.df.groupby(['fiscal_month', 'hw_sw'])['ods_m'].sum().reset_index()
            else:
                monthly = self.df.groupby('fiscal_month')['ods_m'].sum().reset_index()
                monthly['hw_sw'] = 'All'

            fig = go.Figure()
            for cat in monthly['hw_sw'].unique():
                subset = monthly[monthly['hw_sw'] == cat]
                fig.add_trace(go.Scatter(
                    x=subset['fiscal_month'],
                    y=subset['ods_m'],
                    mode='lines+markers',
                    name=str(cat),
                ))

            fig.update_layout(
                title="Monthly Opex Trend (ODS $M)",
                xaxis_title="Fiscal Month",
                yaxis_title="Spend ($M)",
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("View Data Table"):
                if has_hw_sw:
                    pivot = monthly.pivot(
                        index='fiscal_month', columns='hw_sw', values='ods_m'
                    ).fillna(0)
                else:
                    pivot = monthly.set_index('fiscal_month')[['ods_m']]
                st.dataframe(pivot.style.format("${:,.2f}"))
        else:
            missing = []
            if not has_month:
                missing.append("fiscal_month")
            if not has_spend:
                missing.append("ods_m")
            st.info(f"Monthly trend requires columns: {', '.join(missing)}. "
                    "These may not be present in the uploaded data.")

        st.markdown("---")

        # ── Quarterly Run Rate ──
        st.subheader("Quarterly Run Rate")

        has_quarter = 'fiscal_quarter' in self.df.columns and self.df['fiscal_quarter'].notna().any()

        if has_quarter and has_spend:
            if has_hw_sw:
                q_trend = self.df.groupby(['fiscal_quarter', 'hw_sw'])['ods_m'].sum().reset_index()
            else:
                q_trend = self.df.groupby('fiscal_quarter')['ods_m'].sum().reset_index()
                q_trend['hw_sw'] = 'All'

            fig_bar = go.Figure()
            for cat in q_trend['hw_sw'].unique():
                subset = q_trend[q_trend['hw_sw'] == cat]
                fig_bar.add_trace(go.Bar(
                    x=subset['fiscal_quarter'],
                    y=subset['ods_m'],
                    name=str(cat),
                    text=subset['ods_m'].apply(lambda x: f"{x:.1f}"),
                    textposition='auto',
                ))

            fig_bar.update_layout(
                title="Quarterly Spend Accumulation",
                barmode='stack',
                xaxis_title="Fiscal Quarter",
                yaxis_title="Spend ($M)",
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            with st.expander("View Quarterly Data"):
                if has_hw_sw:
                    q_pivot = q_trend.pivot(
                        index='fiscal_quarter', columns='hw_sw', values='ods_m'
                    ).fillna(0)
                else:
                    q_pivot = q_trend.set_index('fiscal_quarter')[['ods_m']]
                q_pivot['Total'] = q_pivot.sum(axis=1)
                st.dataframe(q_pivot.style.format("${:,.2f}"))
        else:
            if not has_quarter:
                st.info("Quarterly trend requires 'fiscal_quarter' column in the data.")
            elif not has_spend:
                st.info("No spend (ods_m) data available.")

        # ── Budget vs Actual Trend ──
        has_budget = 'tm1_m' in self.df.columns
        if has_month and has_spend and has_budget:
            st.markdown("---")
            st.subheader("Budget vs Actual (Monthly)")

            bva = self.df.groupby('fiscal_month').agg(
                Budget=('tm1_m', 'sum'),
                Actual=('ods_m', 'sum'),
            ).reset_index()
            bva['Variance'] = bva['Budget'] - bva['Actual']

            fig_bva = go.Figure()
            fig_bva.add_trace(go.Bar(
                x=bva['fiscal_month'], y=bva['Budget'],
                name='Budget (TM1)', marker_color='#1f77b4',
            ))
            fig_bva.add_trace(go.Bar(
                x=bva['fiscal_month'], y=bva['Actual'],
                name='Actual (ODS)', marker_color='#2ca02c',
            ))
            fig_bva.add_trace(go.Scatter(
                x=bva['fiscal_month'], y=bva['Variance'],
                name='Variance', mode='lines+markers',
                line=dict(color='#d62728', dash='dash'),
            ))
            fig_bva.update_layout(
                title="Budget vs Actual by Month",
                barmode='group',
                xaxis_title="Fiscal Month",
                yaxis_title="$M",
                hovermode="x unified",
            )
            st.plotly_chart(fig_bva, use_container_width=True)


class FinancialTrends(PageBase):
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
                     "AND COALESCE(data_type, 'dollar') = 'dollar' ORDER BY 1")
            with self.db.engine.connect() as conn:
                return [row[0] for row in conn.execute(text(query)).fetchall()]
        except Exception:
            return []

    def get_data(self, project_name: str) -> pd.DataFrame:
        query = ("SELECT * FROM opex_data_hybrid "
                 "WHERE additional_data->>'project_desc' = :pname "
                 "AND COALESCE(data_type, 'dollar') = 'dollar'")
        raw_df = pd.read_sql(text(query), self.db.engine, params={"pname": project_name})

        if not raw_df.empty and 'additional_data' in raw_df.columns:
            json_df = pd.json_normalize(raw_df['additional_data'])
            cols_to_use = json_df.columns.difference(raw_df.columns)
            return pd.concat([raw_df, json_df[cols_to_use]], axis=1)
        return raw_df

    def render(self):
        super().render()
        st.title("Financial Trends Analysis")

        try:
            from utils.models.database import check_opex_db
            ok, err_msg = check_opex_db()
            if not ok:
                st.warning(err_msg)
                return
        except ImportError:
            pass

        if not self.projects:
            st.warning("No projects found.")
            return

        col1, _ = st.columns([1, 2])
        with col1:
            sel_proj = st.selectbox("Select Project", self.projects)

        if sel_proj:
            df = self.get_data(sel_proj)
            if not df.empty:
                dash = FinancialTrendsDashboard(df)
                dash.render()
            else:
                st.warning("No data for selected project.")
