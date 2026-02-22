import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import text

from utils.models.database import OpexDB
from .base import PageBase

class SandboxPage(PageBase):
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
        st.title("Data Plotting Sandbox")
        st.markdown("Generate custom visualizations dynamically.")

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

        col_p, _ = st.columns([1,2])
        with col_p:
            proj = st.selectbox("Select Project Dataset", self.projects)
        
        if proj:
            df = self.get_data(proj)
            if df.empty:
                st.warning("No data.")
                return

            st.markdown("### Chart Configuration")
            col1, col2, col3, col4 = st.columns(4)
            
            numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns.tolist()
            cat_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
            all_cols = df.columns.tolist()

            with col1:
                chart_type = st.selectbox("Chart Type", ["Bar", "Line", "Scatter", "Pie"])
            with col2:
                x_axis = st.selectbox("X Axis", all_cols, index=all_cols.index('fiscal_month') if 'fiscal_month' in all_cols else 0)
            with col3:
                y_axis = st.selectbox("Y Axis (Metric)", numeric_cols, index=numeric_cols.index('ods_mm') if 'ods_mm' in numeric_cols else 0)
            with col4:
                color_dim = st.selectbox("Color / Group By", ["None"] + cat_cols, index=cat_cols.index('hw_sw') + 1 if 'hw_sw' in cat_cols else 0)

            st.markdown("---")
            
            # Dynamic Plot Generation using Graph Objects (Safer for Env)
            try:
                fig = go.Figure()
                
                if color_dim != "None":
                    groups = df[color_dim].unique()
                    for g in groups:
                        subset = df[df[color_dim] == g]
                        # Aggregate if needed to avoid mess
                        if chart_type != "Scatter":
                            subset = subset.groupby(x_axis)[y_axis].sum().reset_index()

                        if chart_type == "Bar":
                            fig.add_trace(go.Bar(x=subset[x_axis], y=subset[y_axis], name=str(g)))
                        elif chart_type == "Line":
                            fig.add_trace(go.Scatter(x=subset[x_axis], y=subset[y_axis], mode='lines+markers', name=str(g)))
                        elif chart_type == "Scatter":
                            fig.add_trace(go.Scatter(x=subset[x_axis], y=subset[y_axis], mode='markers', name=str(g)))
                else:
                    # No Color Grouping
                    agg_df = df.groupby(x_axis)[y_axis].sum().reset_index() if chart_type != "Scatter" else df
                    
                    if chart_type == "Bar":
                        fig.add_trace(go.Bar(x=agg_df[x_axis], y=agg_df[y_axis]))
                    elif chart_type == "Line":
                        fig.add_trace(go.Scatter(x=agg_df[x_axis], y=agg_df[y_axis], mode='lines+markers'))
                    elif chart_type == "Scatter":
                        fig.add_trace(go.Scatter(x=agg_df[x_axis], y=agg_df[y_axis], mode='markers'))
                    elif chart_type == "Pie":
                        fig.add_trace(go.Pie(labels=agg_df[x_axis], values=agg_df[y_axis]))

                fig.update_layout(title=f"{chart_type} Chart: {y_axis} by {x_axis}", barmode='group' if chart_type=='Bar' else None)
                st.plotly_chart(fig, use_container_width=True)

            except Exception as e:
                st.error(f"Could not generate chart: {e}")