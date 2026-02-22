"""
FIRA Welcome Page — Landing page with platform overview and navigation guide.
"""

import streamlit as st
import os
from .base import PageBase


WELCOME_CSS = """
<style>
/* ── Welcome Hero ── */
.welcome-hero {
    text-align: center;
    padding: 2.5rem 2rem 2rem;
    margin-bottom: 1.5rem;
    background: linear-gradient(135deg, #1B5E20 0%, #2E7D32 40%, #388E3C 100%);
    border-radius: 14px;
    position: relative;
    overflow: hidden;
}
.welcome-hero::before {
    content: '';
    position: absolute;
    top: -50%;
    right: -20%;
    width: 500px;
    height: 500px;
    background: radial-gradient(circle, rgba(255,255,255,0.06) 0%, transparent 70%);
    border-radius: 50%;
}
.welcome-hero h2 {
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 800;
    font-size: 2.6rem;
    letter-spacing: 0.08em;
    margin-bottom: 0.15rem;
    position: relative;
}
.welcome-hero .tagline {
    color: #C8E6C9;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 1.05rem;
    font-weight: 400;
    letter-spacing: 0.04em;
    margin-bottom: 0.8rem;
    position: relative;
}
.welcome-hero .version-badge {
    display: inline-block;
    background: rgba(255,255,255,0.15);
    color: #E8F5E9;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    padding: 3px 14px;
    border-radius: 20px;
    letter-spacing: 0.06em;
    position: relative;
}
.welcome-hero .description {
    color: #E8F5E9;
    font-size: 0.92rem;
    line-height: 1.6;
    max-width: 700px;
    margin: 1rem auto 0;
    position: relative;
}

/* ── Quick Start Banner ── */
.quick-start {
    background: linear-gradient(90deg, #FFF8E1 0%, #FFFDE7 100%);
    border: 1px solid #F9A825;
    border-left: 4px solid #8B6914;
    border-radius: 10px;
    padding: 1rem 1.5rem;
    margin-bottom: 1.5rem;
}
.quick-start h4 {
    color: #6D5210 !important;
    margin: 0 0 0.3rem 0;
    font-size: 1rem;
}
.quick-start p {
    color: #5D4E37 !important;
    font-size: 0.88rem;
    margin: 0;
    line-height: 1.5;
}

/* ── Section Card ── */
.section-card {
    background: #FFFFFF;
    border: 1px solid #C8DCC8;
    border-radius: 10px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.9rem;
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
    min-height: 150px;
}
.section-card:hover {
    box-shadow: 0 4px 16px rgba(27,94,32,0.10);
    border-color: #2E7D32;
}
.section-card .card-icon {
    font-size: 1.6rem;
    margin-bottom: 0.4rem;
}
.section-card h4 {
    color: #1B5E20 !important;
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 700;
    font-size: 1rem;
    margin: 0 0 0.4rem 0;
}
.section-card p {
    color: #4A6B4A !important;
    font-size: 0.85rem;
    line-height: 1.55;
    margin: 0;
}
.section-card .card-tag {
    display: inline-block;
    background: #E8F5E9;
    color: #2E7D32;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 4px;
    margin-top: 0.5rem;
    letter-spacing: 0.03em;
}

/* ── Section Headers ── */
.section-header {
    color: #1B5E20;
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 700;
    font-size: 1.15rem;
    margin: 1.5rem 0 0.8rem;
    padding-bottom: 0.4rem;
    border-bottom: 2px solid #2E7D32;
}

/* ── Footer ── */
.welcome-footer {
    text-align: center;
    padding: 1.2rem 0;
    margin-top: 1.5rem;
    border-top: 1px solid #C8DCC8;
    color: #7A9A7A;
    font-size: 0.8rem;
}
</style>
"""


class Welcome(PageBase):
    """FIRA Welcome / Landing page."""

    def render(self):
        # Don't call super().render() — we handle our own header
        st.query_params.clear()
        if self.url:
            st.query_params["page"] = self.url
        try:
            from ui.streamlit_tools import app_css
            app_css()
        except ImportError:
            pass

        st.markdown(WELCOME_CSS, unsafe_allow_html=True)

        # ── FIRA Logo (inline SVG) ──
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fira_logo.svg")
        logo_svg = ""
        if os.path.exists(logo_path):
            with open(logo_path) as f:
                logo_svg = f.read()

        # ── Hero Section ──
        st.markdown(
            f"""
            <div class="welcome-hero">
                <h2>FIRA</h2>
                <div class="tagline">Financial Intelligence &amp; Resource Analytics</div>
                <div class="version-badge">v2.1 &nbsp;&bull;&nbsp; Enterprise Edition</div>
                <p class="description">
                    A unified platform combining interactive resource planning, AI-powered data analysis,
                    and comprehensive OpEx intelligence &mdash; built for finance teams that demand precision.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Quick Start ──
        st.markdown(
            """
            <div class="quick-start">
                <h4>Getting Started</h4>
                <p>
                    <strong>Step 1:</strong> Go to <strong>Data Mgmt</strong> to upload your OpEx, Resource Planner, or Headcount data.
                    &nbsp;&bull;&nbsp;
                    <strong>Step 2:</strong> Explore dashboards like <strong>Resource Planner</strong> and <strong>OpEx Summary</strong>.
                    &nbsp;&bull;&nbsp;
                    <strong>Step 3:</strong> Ask the <strong>AI ChatBot</strong> any financial or resource question in plain English.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Data & Planning ──
        st.markdown('<div class="section-header">Data &amp; Planning</div>', unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown(
                """
                <div class="section-card">
                    <div class="card-icon">&#128202;</div>
                    <h4>Data Management</h4>
                    <p>
                        Upload and ingest OpEx Excel files, Resource Planner CSVs, and Headcount data.
                        Monitor table health with real-time row counts. Re-ingest data anytime.
                    </p>
                    <span class="card-tag">Upload &bull; Ingest &bull; Monitor</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col2:
            st.markdown(
                """
                <div class="section-card">
                    <div class="card-icon">&#9968;</div>
                    <h4>Resource Planner</h4>
                    <p>
                        Interactive mountain chart with demand vs. capacity analysis. Priority-based
                        project stacking, per-country cost controls, and snapshot save/load.
                    </p>
                    <span class="card-tag">Capacity &bull; Demand &bull; Scenarios</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col3:
            st.markdown(
                """
                <div class="section-card">
                    <div class="card-icon">&#129302;</div>
                    <h4>AI ChatBot</h4>
                    <p>
                        Ask financial or resource questions in plain English. Get executive-quality analysis
                        with auto-generated charts, powered by a multi-agent AI pipeline.
                    </p>
                    <span class="card-tag">NLP &bull; SQL &bull; RAG &bull; Charts</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # ── Financial Analytics ──
        st.markdown('<div class="section-header">Financial Analytics</div>', unsafe_allow_html=True)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown(
                """
                <div class="section-card">
                    <div class="card-icon">&#128200;</div>
                    <h4>OpEx Summary</h4>
                    <p>
                        Executive dashboard with FY summary, project spend breakdown, and LOE analysis.
                    </p>
                    <span class="card-tag">Executive View</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col2:
            st.markdown(
                """
                <div class="section-card">
                    <div class="card-icon">&#128201;</div>
                    <h4>Financial Trends</h4>
                    <p>
                        Time-series analysis across fiscal periods. Track spending patterns and identify anomalies.
                    </p>
                    <span class="card-tag">Trend Analysis</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col3:
            st.markdown(
                """
                <div class="section-card">
                    <div class="card-icon">&#127758;</div>
                    <h4>Geo &amp; Org Analytics</h4>
                    <p>
                        Country-level cost comparisons and organizational spending metrics by region and department.
                    </p>
                    <span class="card-tag">Geographic View</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col4:
            st.markdown(
                """
                <div class="section-card">
                    <div class="card-icon">&#127959;</div>
                    <h4>Dept Rollup</h4>
                    <p>
                        Department-level cost aggregation and VP rollup analysis for organizational budgeting.
                    </p>
                    <span class="card-tag">Dept Costs</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # ── Tools & Utilities ──
        st.markdown('<div class="section-header">Tools &amp; Utilities</div>', unsafe_allow_html=True)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown(
                """
                <div class="section-card">
                    <div class="card-icon">&#128101;</div>
                    <h4>Resource Allocation</h4>
                    <p>
                        Resource utilization rates and allocation optimization views across projects and teams.
                    </p>
                    <span class="card-tag">Utilization</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col2:
            st.markdown(
                """
                <div class="section-card">
                    <div class="card-icon">&#127912;</div>
                    <h4>Plotting Sandbox</h4>
                    <p>
                        Custom visualization builder for ad-hoc analysis. Create your own charts from any data.
                    </p>
                    <span class="card-tag">Custom Charts</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col3:
            st.markdown(
                """
                <div class="section-card">
                    <div class="card-icon">&#128172;</div>
                    <h4>FAQ</h4>
                    <p>
                        Searchable frequently asked questions about the platform, features, and usage tips.
                    </p>
                    <span class="card-tag">Help</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col4:
            st.markdown(
                """
                <div class="section-card">
                    <div class="card-icon">&#128337;</div>
                    <h4>Chat History</h4>
                    <p>
                        Browse and review past AI chat sessions. Export conversations for audit and reference.
                    </p>
                    <span class="card-tag">Admin</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # ── Footer ──
        st.markdown(
            """
            <div class="welcome-footer">
                FIRA &mdash; Financial Intelligence &amp; Resource Analytics &nbsp;&bull;&nbsp;
                v2.1 &nbsp;&bull;&nbsp; Built for Enterprise Finance Teams
            </div>
            """,
            unsafe_allow_html=True,
        )
