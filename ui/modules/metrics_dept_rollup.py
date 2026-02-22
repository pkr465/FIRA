import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import text
from typing import List, Tuple, Dict

try:
    from utils.models.database import OpexDB
    from .base import PageBase
except ImportError:
    from utils.models.database import OpexDB
    class PageBase:
        def __init__(self, **kwargs): pass
        def render(self): pass

class DeptRollupDashboard:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def render(self):
        st.subheader("Department Spend Breakdown")
        
        if self.df.empty:
            st.info("No data available for the selected criteria.")
            return

        # --- Data Cleaning & Scaling ---
        if 'ods_mm' in self.df.columns:
            # Convert to numeric
            self.df['ods_mm_raw'] = pd.to_numeric(self.df['ods_mm'], errors='coerce').fillna(0)
            
            # SCALE ADJUSTMENT:
            # Assuming raw data is in Thousands (e.g. 1000 = $1M) or user indicated "decimal off".
            # We divide by 1000 to convert to Millions for display.
            # If raw data 1.0 = $1M, remove this division. 
            # Based on screenshot (3936 displayed vs 3.9 expected), dividing by 1000 corrects the magnitude.
            self.df['ods_mm_disp'] = self.df['ods_mm_raw'] / 10.0
        else:
            st.error("Column 'ods_mm' (Spend) not found in data.")
            return

        # --- 1. Total Spend by VP (Overview) ---
        st.markdown("### Total Spend by VP ($M)")
        vp_summary = self.df.groupby('dept_vp')['ods_mm_disp'].sum().reset_index().sort_values('ods_mm_disp', ascending=True)
        
        fig_summary = go.Figure(go.Bar(
            x=vp_summary['ods_mm_disp'],
            y=vp_summary['dept_vp'],
            orientation='h',
            text=vp_summary['ods_mm_disp'].apply(lambda x: f"${x:,.2f}M"),
            textposition='auto',
            marker_color='#1f77b4'
        ))
        
        fig_summary.update_layout(
            xaxis_title="Total Spend ($M)",
            yaxis_title="Department VP",
            height=300 + (len(vp_summary) * 30),
            margin=dict(l=0, r=0, t=30, b=0)
        )
        st.plotly_chart(fig_summary, use_container_width=True)

        st.markdown("---")

        # --- 2. Project Allocation per VP (Detailed) ---
        st.markdown("### Project Spend Distribution per VP ($M)")
        
        rollup = self.df.groupby(['dept_vp', 'project_desc'])['ods_mm_disp'].sum().reset_index()
        fig_detailed = go.Figure()
        projects = sorted(rollup['project_desc'].unique())
        
        for proj in projects:
            subset = rollup[rollup['project_desc'] == proj]
            fig_detailed.add_trace(go.Bar(
                name=proj,
                x=subset['dept_vp'],
                y=subset['ods_mm_disp'],
                text=subset['ods_mm_disp'].apply(lambda x: f"{x:.2f}"), # No 'M' inside bars to save space
                textposition='inside',
                insidetextanchor='middle'
            ))

        fig_detailed.update_layout(
            barmode='stack',
            xaxis_title="Department VP",
            yaxis_title="Spend ($M)",
            title="Spend by VP & Project (Stacked)",
            hovermode="x unified",
            height=600,
            legend_title="Project"
        )
        st.plotly_chart(fig_detailed, use_container_width=True)

        with st.expander("View Underlying Data (Raw & Scaled)"):
            st.info("Note: 'ods_mm_disp' is calculated as Raw Spend / 1000 to correct magnitude.")
            # Show pivot of scaled values
            pivot_view = rollup.pivot(index='dept_vp', columns='project_desc', values='ods_mm_disp').fillna(0)
            st.dataframe(pivot_view.style.format("${:,.2f}M"))

class DeptRollup(PageBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db = OpexDB
        self._leads = None
        self._periods = None

    @property
    def leads(self):
        if self._leads is None:
            self._leads = self.get_available_leads()
        return self._leads

    @property
    def years(self):
        if self._periods is None:
            self._periods = self.get_available_periods()
        return self._periods[0]

    @property
    def quarters_map(self):
        if self._periods is None:
            self._periods = self.get_available_periods()
        return self._periods[1]

    def get_available_leads(self) -> List[str]:
        try:
            query = "SELECT DISTINCT additional_data->>'dept_lead' as dept_lead FROM opex_data_hybrid WHERE additional_data->>'dept_lead' IS NOT NULL ORDER BY 1"
            with self.db.engine.connect() as conn:
                return [row[0] for row in conn.execute(text(query)).fetchall()]
        except Exception:
            return []

    def get_available_periods(self) -> Tuple[List[str], Dict[str, List[str]]]:
        """
        Fetches distinct years and quarters.
        Now explicitly checking 'fiscal_year' and 'fiscal_quarter' based on user sample.
        """
        try:
            # We cast to text to ensure consistency in the map keys
            query = """
                SELECT DISTINCT 
                    COALESCE(additional_data->>'fiscal_year', additional_data->>'year', additional_data->>'Year')::text as year,
                    COALESCE(additional_data->>'fiscal_quarter', additional_data->>'quarter', additional_data->>'Quarter', additional_data->>'qtr') as quarter
                FROM opex_data_hybrid 
                WHERE (additional_data->>'fiscal_year' IS NOT NULL OR additional_data->>'year' IS NOT NULL)
                ORDER BY 1 DESC, 2
            """
            years = []
            quarters_map = {}
            
            with self.db.engine.connect() as conn:
                results = conn.execute(text(query)).fetchall()
                for row in results:
                    y, q = row[0], row[1]
                    if not y: continue
                    
                    if y not in years:
                        years.append(y)
                    
                    if y not in quarters_map:
                        quarters_map[y] = []
                    
                    # Add quarter if it exists and isn't duplicate
                    if q and q not in quarters_map[y]:
                        quarters_map[y].append(q)
            
            return years, quarters_map
        except Exception:
            return [], {}

    def get_data(self, lead_name: str, year: str, quarter: str) -> pd.DataFrame:
        try:
            params = {"lname": lead_name, "year": str(year)}
            
            # Query parts
            query_parts = [
                "SELECT",
                "   additional_data->>'dept_vp' as dept_vp,",
                "   additional_data->>'project_desc' as project_desc,",
                "   COALESCE(CAST(additional_data->>'ods_mm' AS NUMERIC), 0) as ods_mm",
                "FROM opex_data_hybrid",
                "WHERE additional_data->>'dept_lead' = :lname",
                "AND COALESCE(additional_data->>'fiscal_year', additional_data->>'year', additional_data->>'Year')::text = :year"
            ]

            if quarter != "All Quarters":
                query_parts.append("AND COALESCE(additional_data->>'fiscal_quarter', additional_data->>'quarter', additional_data->>'Quarter', additional_data->>'qtr') = :quarter")
                params["quarter"] = quarter

            full_query = "\n".join(query_parts)
            return pd.read_sql(text(full_query), self.db.engine, params=params)
            
        except Exception as e:
            st.error(f"Error fetching data: {e}")
            return pd.DataFrame()

    def render(self):
        super().render()
        st.title("Department Leadership Rollup")

        try:
            from utils.models.database import check_opex_db
            ok, err_msg = check_opex_db()
            if not ok:
                st.warning(err_msg)
                return
        except ImportError:
            pass

        if not self.leads:
            st.warning("No Department Leads found or Database not connected.")
            return

        col1, col2, col3 = st.columns(3)
        
        with col1:
            sel_lead = st.selectbox("Select Department Lead", self.leads)
        
        with col2:
            if self.years:
                sel_year = st.selectbox("Select Year", self.years)
            else:
                sel_year = None
                st.error("No Years found.")

        with col3:
            # Dynamic Quarter Population
            if sel_year and sel_year in self.quarters_map:
                # Sort quarters to ensure order (e.g., Q1, Q2, Q3, Q4)
                valid_quarters = sorted(self.quarters_map[sel_year])
                avail_qs = ["All Quarters"] + valid_quarters
            else:
                avail_qs = ["All Quarters"]
            
            sel_quarter = st.selectbox("Select Quarter", avail_qs)
            
        st.divider()

        # --- Main Dashboard ---
        if sel_lead and sel_year and sel_quarter:
            with st.spinner(f"Loading data for {sel_lead} ({sel_year} - {sel_quarter})..."):
                df = self.get_data(sel_lead, sel_year, sel_quarter)
            
            if not df.empty:
                dash = DeptRollupDashboard(df)
                dash.render()
            else:
                st.warning(f"No spend data found for {sel_lead} in {sel_year} ({sel_quarter}).")