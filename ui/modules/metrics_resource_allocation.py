import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import text

from utils.models.database import OpexDB
from .base import PageBase

class ResourceDashboard:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def render(self):
        st.subheader("Workforce Composition (TM1 MM)")
        
        # 1. Composition: Reg vs Temp vs FTA (Using 'exp_type_r5' or 'exp_type_r3')
        # Fallback logic for columns
        col_type = 'exp_type_r5' if 'exp_type_r5' in self.df.columns else 'exp_type_r3'
        
        if col_type in self.df.columns and 'tm1_mm' in self.df.columns:
            comp_df = self.df.groupby([col_type])['tm1_mm'].sum().reset_index()
            
            col1, col2 = st.columns(2)
            with col1:
                fig_pie = go.Figure(data=[go.Pie(labels=comp_df[col_type], values=comp_df['tm1_mm'], hole=.3)])
                fig_pie.update_layout(title="Headcount by Type")
                st.plotly_chart(fig_pie, use_container_width=True)
            
            with col2:
                # HC by HW/SW
                hs_df = self.df.groupby(['hw_sw', col_type])['tm1_mm'].sum().reset_index()
                fig_bar = go.Figure()
                for t in hs_df[col_type].unique():
                    subset = hs_df[hs_df[col_type] == t]
                    fig_bar.add_trace(go.Bar(x=subset['hw_sw'], y=subset['tm1_mm'], name=str(t)))
                
                fig_bar.update_layout(title="HC Distribution by Tech", barmode='stack')
                st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")
        st.subheader("Cross Charge & Adjustments")
        
        # 2. Cross Charge Analysis
        if 'exp_type_r3' in self.df.columns:
            cc_data = self.df.groupby(['exp_type_r3'])['tm1_mm'].sum().reset_index()
            cc_data = cc_data.sort_values('tm1_mm', ascending=False)
            
            st.info("Note: Positive values = Direct HC or In-charges. Negative values = Out-charges (Credits).")
            st.dataframe(
                cc_data.style.format({'tm1_mm': '{:,.2f}'}),
                use_container_width=True
            )

class ResourceAllocation(PageBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db = OpexDB
        self._projects = None

    @property
    def projects(self):
        if self._projects is None:
            self._projects = self.get_available_projects()
        return self._projects

    def get_available_projects(self):
        try:
            query = "SELECT DISTINCT additional_data->>'project_desc' FROM opex_data_hybrid WHERE additional_data->>'project_desc' IS NOT NULL ORDER BY 1"
            with self.db.engine.connect() as conn:
                return [row[0] for row in conn.execute(text(query)).fetchall()]
        except: return []

    def get_data(self, project_name):
        query = "SELECT * FROM opex_data_hybrid WHERE additional_data->>'project_desc' = :p"
        raw = pd.read_sql(text(query), self.db.engine, params={"p": project_name})
        if not raw.empty and 'additional_data' in raw.columns:
            json_df = pd.json_normalize(raw['additional_data'])
            cols = json_df.columns.difference(raw.columns)
            return pd.concat([raw, json_df[cols]], axis=1)
        return raw

    def render(self):
        super().render()
        st.title("Resource & Headcount Analytics")

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
            proj = st.selectbox("Select Project", self.projects)
            
        if proj:
            df = self.get_data(proj)
            if not df.empty:
                ResourceDashboard(df).render()