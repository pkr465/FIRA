import streamlit as st
import pandas as pd
import json
import plotly.graph_objects as go
from sqlalchemy import text
from ui.modules.base import PageBase
from utils.models.database import OpexDB

class GeoOrgMetrics(PageBase):
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
        """Fetch list of available projects."""
        try:
            query = """
            SELECT DISTINCT additional_data->>'project_desc' 
            FROM opex_data_hybrid 
            WHERE additional_data->>'project_desc' IS NOT NULL 
            ORDER BY 1
            """
            with self.db.engine.connect() as conn:
                return [row[0] for row in conn.execute(text(query)).fetchall()]
        except Exception:
            return []

    def _to_iso3(self, val):
        """Maps country names to ISO-3 standard for Plotly."""
        if not isinstance(val, str):
            return None
        
        clean = val.strip().upper()
        
        iso_map = {
            'USA': 'USA', 'US': 'USA', 'UNITED STATES': 'USA',
            'INDIA': 'IND', 'IND': 'IND', 'IN': 'IND',
            'CHINA': 'CHN', 'CHN': 'CHN', 'PRC': 'CHN',
            'ISRAEL': 'ISR', 'ISR': 'ISR',
            'UK': 'GBR', 'UNITED KINGDOM': 'GBR', 'GB': 'GBR',
            'TAIWAN': 'TWN', 'TW': 'TWN',
            'KOREA': 'KOR', 'SOUTH KOREA': 'KOR',
            'JAPAN': 'JPN', 'JP': 'JPN',
            'GERMANY': 'DEU', 'DE': 'DEU',
            'CANADA': 'CAN', 'CA': 'CAN',
            'FRANCE': 'FRA', 'FR': 'FRA',
            'SINGAPORE': 'SGP', 'SG': 'SGP',
            'IRELAND': 'IRL', 'IE': 'IRL',
            'NETHERLANDS': 'NLD', 'NL': 'NLD',
            'VIETNAM': 'VNM', 'VN': 'VNM'
        }
        return iso_map.get(clean, None)

    def get_project_data(self, project_name):
        """Fetch and clean data, specifically targeting R1 (Country) and R2 (City)."""
        try:
            query = "SELECT * FROM opex_data_hybrid WHERE additional_data->>'project_desc' = :p"
            raw = pd.read_sql(text(query), self.db.engine, params={"p": project_name})
            
            if not raw.empty and 'additional_data' in raw.columns:
                # 1. Normalize JSON (Handle String or Dict)
                # Ensure we are working with a list of dicts
                data_list = []
                raw_items = raw['additional_data'].dropna()
                
                if not raw_items.empty:
                    first_item = raw_items.iloc[0]
                    if isinstance(first_item, str):
                        # If DB returns strings, parse them
                        data_list = [json.loads(x) for x in raw_items]
                    else:
                        data_list = raw_items.tolist()
                
                if not data_list:
                    return raw
                    
                json_df = pd.json_normalize(data_list)
                
                # Merge
                raw_reset = raw.reset_index(drop=True)
                cols = json_df.columns.difference(raw_reset.columns)
                df = pd.concat([raw_reset, json_df[cols]], axis=1)
                
                # 2. Column Mapping Helper
                def get_col(candidates):
                    col_map = {c.lower().replace(' ', '').replace('_', ''): c for c in df.columns}
                    for cand in candidates:
                        clean = cand.lower().replace(' ', '').replace('_', '')
                        if clean in col_map:
                            return col_map[clean]
                    return None

                # 3. Identify Specific Columns
                # R1 = Country (USA, India) - Explicitly checking homedeptregionr1
                r1_col = get_col(['homedeptregionr1', 'homedeptregion', 'country', 'geo'])
                
                # R2 = City/Location (San Jose, Chennai) - Explicitly checking homedeptregionr2
                r2_col = get_col(['homedeptregionr2', 'location', 'city', 'site'])
                
                # VP & Spend
                vp_col = get_col(['homedeptvprollup1', 'homedeptvprollup2', 'homedeptvp', 'vpname'])
                ods_col = get_col(['odsmm', 'ods', 'spend'])
                
                # 4. Process Data
                # Country (R1)
                if r1_col:
                    df['ISO3'] = df[r1_col].apply(self._to_iso3)
                    df['Country_Label'] = df[r1_col]
                else:
                    df['ISO3'] = None
                    df['Country_Label'] = 'Unknown'
                
                # Location (R2)
                if r2_col:
                    df['Location_Label'] = df[r2_col].fillna('Unknown')
                else:
                    df['Location_Label'] = 'Unknown'

                # VP
                if vp_col:
                    df['VP_Name'] = df[vp_col].fillna('Unknown')
                else:
                    df['VP_Name'] = 'Unknown'
                
                # Metrics
                target_ods = ods_col if ods_col else 'ods_mm'
                if target_ods in df.columns:
                    df['ods_mm'] = pd.to_numeric(df[target_ods], errors='coerce').fillna(0)
                else:
                    df['ods_mm'] = 0.0

                return df
            return raw
        except Exception as e:
            st.error(f"Error loading data: {e}")
            return pd.DataFrame()

    def render(self):
        super().render()
        st.title("Geo & Organizational Analytics")

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

        selected_project = st.selectbox("Select Project", self.projects)

        if selected_project:
            df = self.get_project_data(selected_project)
            if df.empty:
                st.warning("No data available.")
                return

            # --- 1. Global Footprint (Map using R1) ---
            st.subheader("Global Footprint")
            st.caption("Spend Concentration by Country (Source: Home Dept Region R1)")

            if 'ISO3' in df.columns:
                geo_agg = df.groupby(['ISO3', 'Country_Label'])['ods_mm'].sum().reset_index()
                geo_agg = geo_agg[geo_agg['ods_mm'].abs() > 0.001]

                if not geo_agg.empty:
                    # Fix for single value color scaling
                    z_min = geo_agg['ods_mm'].min()
                    z_max = geo_agg['ods_mm'].max()
                    if z_min == z_max:
                        z_min = 0
                    
                    fig_map = go.Figure(data=go.Choropleth(
                        locations=geo_agg['ISO3'],
                        locationmode='ISO-3',
                        z=geo_agg['ods_mm'],
                        text=geo_agg['Country_Label'],
                        colorscale='Blues',
                        zmin=z_min, 
                        zmax=z_max,
                        marker_line_color='darkgray',
                        marker_line_width=0.5,
                        colorbar_title="Spend ($M)"
                    ))
                    fig_map.update_layout(
                        geo=dict(
                            showframe=False, 
                            showcoastlines=True, 
                            projection_type='equirectangular',
                            showland=True,
                            landcolor="#f0f0f0"
                        ),
                        margin={"r":0,"t":0,"l":0,"b":0},
                        height=500
                    )
                    st.plotly_chart(fig_map, use_container_width=True)
                else:
                    st.info("No valid country data found for mapping.")
            
            st.markdown("---")

            # --- 2. Location Breakdown (Table/Chart using R2) ---
            st.subheader("Location Breakdown")
            st.caption("Spend by Site/City (Source: Home Dept Region R2)")
            
            if 'Location_Label' in df.columns:
                loc_agg = df.groupby('Location_Label')['ods_mm'].sum().sort_values(ascending=False).reset_index()
                loc_agg = loc_agg[loc_agg['ods_mm'].abs() > 0.001]
                
                if not loc_agg.empty:
                    # Display as a horizontal bar chart
                    fig_loc = go.Figure(go.Bar(
                        x=loc_agg['ods_mm'],
                        y=loc_agg['Location_Label'],
                        orientation='h',
                        text=loc_agg['ods_mm'].apply(lambda x: f"${x:,.2f}M"),
                        textposition='auto',
                        marker_color='#00CC96'
                    ))
                    fig_loc.update_layout(
                        yaxis=dict(autorange="reversed"), # Top spenders at top
                        xaxis_title="Spend ($M)",
                        height=max(300, len(loc_agg)*30),
                        margin=dict(l=20, r=20, t=20, b=20)
                    )
                    st.plotly_chart(fig_loc, use_container_width=True)
                else:
                    st.info("No location (R2) data available.")
            
            st.markdown("---")

            # --- 3. Leadership ---
            st.subheader("Organizational Leadership")
            st.caption("Total Spend by VP Rollup")

            if 'VP_Name' in df.columns:
                vp_agg = df.groupby('VP_Name')['ods_mm'].sum().sort_values(ascending=True).reset_index()
                vp_agg = vp_agg[vp_agg['ods_mm'].abs() > 0.01]

                if not vp_agg.empty:
                    fig_vp = go.Figure(go.Bar(
                        x=vp_agg['ods_mm'],
                        y=vp_agg['VP_Name'],
                        orientation='h',
                        text=vp_agg['ods_mm'].apply(lambda x: f"${x:,.1f}M"),
                        textposition='auto',
                        marker_color='#636EFA'
                    ))
                    fig_vp.update_layout(
                        xaxis_title="Spend ($M)",
                        height=max(400, len(vp_agg)*40),
                        margin=dict(l=20, r=20, t=20, b=20)
                    )
                    st.plotly_chart(fig_vp, use_container_width=True)