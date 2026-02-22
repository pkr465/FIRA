import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import text
from typing import List

from utils.models.database import OpexDB
from .base import PageBase

class FinancialTrendsDashboard:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        # Sort months fiscally (Oct start)
        self.month_order = ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep']
        if 'fiscal_month' in self.df.columns:
            self.df['fiscal_month'] = pd.Categorical(self.df['fiscal_month'], categories=self.month_order, ordered=True)
            self.df = self.df.sort_values('fiscal_month')

    def render(self):
        st.subheader("Monthly Spend Trend ($M)")
        
        if 'fiscal_month' in self.df.columns and 'ods_mm' in self.df.columns:
            # Aggregate
            monthly = self.df.groupby(['fiscal_month', 'hw_sw'])['ods_mm'].sum().reset_index()
            
            # Create Plotly Graph Object Figure
            fig = go.Figure()
            for cat in monthly['hw_sw'].unique():
                subset = monthly[monthly['hw_sw'] == cat]
                fig.add_trace(go.Scatter(
                    x=subset['fiscal_month'], 
                    y=subset['ods_mm'], 
                    mode='lines+markers', 
                    name=str(cat)
                ))
            
            fig.update_layout(
                title="Monthly Opex Trend (ODS MM)",
                xaxis_title="Fiscal Month",
                yaxis_title="Spend ($M)",
                hovermode="x unified"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("View Data Table"):
                pivot = monthly.pivot(index='fiscal_month', columns='hw_sw', values='ods_mm').fillna(0)
                st.dataframe(pivot.style.format("${:,.2f}"))

        st.markdown("---")
        st.subheader("Quarterly Run Rate")
        
        if 'fiscal_quarter' in self.df.columns:
            q_trend = self.df.groupby(['fiscal_quarter', 'hw_sw'])['ods_mm'].sum().reset_index()
            
            fig_bar = go.Figure()
            for cat in q_trend['hw_sw'].unique():
                subset = q_trend[q_trend['hw_sw'] == cat]
                fig_bar.add_trace(go.Bar(
                    x=subset['fiscal_quarter'], 
                    y=subset['ods_mm'], 
                    name=str(cat),
                    text=subset['ods_mm'].apply(lambda x: f"{x:.1f}"),
                    textposition='auto'
                ))
                
            fig_bar.update_layout(title="Quarterly Spend Accumulation", barmode='stack')
            st.plotly_chart(fig_bar, use_container_width=True)

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
            query = "SELECT DISTINCT additional_data->>'project_desc' as project FROM opex_data_hybrid WHERE additional_data->>'project_desc' IS NOT NULL ORDER BY 1"
            with self.db.engine.connect() as conn:
                return [row[0] for row in conn.execute(text(query)).fetchall()]
        except Exception:
            return []

    def get_data(self, project_name: str) -> pd.DataFrame:
        query = "SELECT * FROM opex_data_hybrid WHERE additional_data->>'project_desc' = :pname"
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