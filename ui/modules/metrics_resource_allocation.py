import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import text

from utils.models.database import OpexDB
from .base import PageBase


class ResourceDashboard:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

        # Coerce key numeric columns
        for col in ['tm1_mm', 'ods_mm']:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce').fillna(0)

    def render(self):
        st.subheader("Workforce Composition (TM1 MM)")

        # Determine the best type column (fallback chain)
        col_type = None
        for candidate in ['exp_type_r5', 'exp_type_r3', 'hw_sw']:
            if candidate in self.df.columns and self.df[candidate].notna().any():
                col_type = candidate
                break

        has_tm1 = 'tm1_mm' in self.df.columns
        has_hw_sw = 'hw_sw' in self.df.columns and self.df['hw_sw'].notna().any()

        if not has_tm1:
            st.info("No workforce data available (tm1_mm column missing).")
            return

        # Summary metrics
        total_tm1 = self.df['tm1_mm'].sum()
        total_ods = self.df['ods_mm'].sum() if 'ods_mm' in self.df.columns else 0
        m1, m2, m3 = st.columns(3)
        m1.metric("Total HC (TM1 MM)", f"{total_tm1:,.1f}")
        m2.metric("Total Spend (ODS MM)", f"${total_ods:,.2f}M")
        if col_type:
            m3.metric("Resource Types", self.df[col_type].nunique())
        st.markdown("")

        # 1. Composition breakdown
        if col_type and has_tm1:
            comp_df = self.df.groupby(col_type)['tm1_mm'].sum().reset_index()

            col1, col2 = st.columns(2)
            with col1:
                fig_pie = go.Figure(data=[go.Pie(
                    labels=comp_df[col_type],
                    values=comp_df['tm1_mm'],
                    hole=.3,
                    textinfo='label+percent',
                    hovertemplate="<b>%{label}</b><br>HC: %{value:,.1f}<br>%{percent}<extra></extra>",
                )])
                fig_pie.update_layout(title=f"Headcount by {col_type}")
                st.plotly_chart(fig_pie, use_container_width=True)

            with col2:
                if has_hw_sw:
                    hs_df = self.df.groupby(['hw_sw', col_type])['tm1_mm'].sum().reset_index()
                    fig_bar = go.Figure()
                    for t in hs_df[col_type].unique():
                        subset = hs_df[hs_df[col_type] == t]
                        fig_bar.add_trace(go.Bar(
                            x=subset['hw_sw'], y=subset['tm1_mm'], name=str(t),
                        ))
                    fig_bar.update_layout(
                        title="HC Distribution by HW/SW",
                        barmode='stack',
                        xaxis_title="HW / SW",
                        yaxis_title="HC (TM1 MM)",
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)
                else:
                    # Show by type as bar chart instead
                    fig_bar = go.Figure(go.Bar(
                        x=comp_df[col_type], y=comp_df['tm1_mm'],
                        text=comp_df['tm1_mm'].apply(lambda x: f"{x:,.1f}"),
                        textposition='auto',
                    ))
                    fig_bar.update_layout(
                        title=f"HC by {col_type}",
                        xaxis_title=col_type,
                        yaxis_title="HC (TM1 MM)",
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)

            with st.expander("View Composition Data"):
                comp_df = comp_df.sort_values('tm1_mm', ascending=False)
                comp_df['% of Total'] = (comp_df['tm1_mm'] / comp_df['tm1_mm'].sum() * 100).round(1)
                st.dataframe(comp_df.style.format({'tm1_mm': '{:,.2f}', '% of Total': '{:.1f}%'}))
        else:
            st.info("No resource type breakdown available. "
                    "Upload data with exp_type_r5, exp_type_r3, or hw_sw columns.")

        st.markdown("---")

        # 2. Cross Charge Analysis
        st.subheader("Cross Charge & Adjustments")

        if 'exp_type_r3' in self.df.columns and self.df['exp_type_r3'].notna().any():
            cc_data = self.df.groupby('exp_type_r3')['tm1_mm'].sum().reset_index()
            cc_data = cc_data.sort_values('tm1_mm', ascending=False)

            st.info("Positive values = Direct HC or In-charges. Negative values = Out-charges (Credits).")

            # Color-code positive/negative
            fig_cc = go.Figure(go.Bar(
                x=cc_data['exp_type_r3'],
                y=cc_data['tm1_mm'],
                marker_color=['#2ca02c' if v >= 0 else '#d62728' for v in cc_data['tm1_mm']],
                text=cc_data['tm1_mm'].apply(lambda x: f"{x:,.1f}"),
                textposition='auto',
            ))
            fig_cc.update_layout(
                title="Cross Charge Analysis",
                xaxis_title="Expense Type (R3)",
                yaxis_title="HC (TM1 MM)",
                height=400,
            )
            st.plotly_chart(fig_cc, use_container_width=True)

            with st.expander("View Cross Charge Data"):
                st.dataframe(
                    cc_data.style.format({'tm1_mm': '{:,.2f}'}),
                    use_container_width=True,
                )
        else:
            st.info("No cross-charge data available (exp_type_r3 column missing).")

        # 3. HC by Department Lead (if available)
        if 'dept_lead' in self.df.columns and self.df['dept_lead'].notna().any():
            st.markdown("---")
            st.subheader("HC by Department Lead")

            lead_data = self.df.groupby('dept_lead')['tm1_mm'].sum().sort_values(ascending=True).reset_index()
            lead_data = lead_data[lead_data['tm1_mm'].abs() > 0.01]

            if not lead_data.empty:
                fig_lead = go.Figure(go.Bar(
                    x=lead_data['tm1_mm'],
                    y=lead_data['dept_lead'],
                    orientation='h',
                    text=lead_data['tm1_mm'].apply(lambda x: f"{x:,.1f}"),
                    textposition='auto',
                    marker_color='#636EFA',
                ))
                fig_lead.update_layout(
                    xaxis_title="HC (TM1 MM)",
                    height=max(300, len(lead_data) * 30),
                    margin=dict(l=20, r=20, t=20, b=20),
                )
                st.plotly_chart(fig_lead, use_container_width=True)


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
            query = ("SELECT DISTINCT additional_data->>'project_desc' "
                     "FROM opex_data_hybrid "
                     "WHERE additional_data->>'project_desc' IS NOT NULL ORDER BY 1")
            with self.db.engine.connect() as conn:
                return [row[0] for row in conn.execute(text(query)).fetchall()]
        except Exception:
            return []

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
            else:
                st.warning("No data for selected project.")
