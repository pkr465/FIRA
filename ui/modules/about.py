import streamlit as st
from .base import PageBase


ABOUT_CSS = """
<style>
.about-container {
    max-width: 900px;
    margin: 0 auto;
    padding: 0 1rem;
}
.about-hero {
    text-align: center;
    padding: 2rem 1rem;
    margin-bottom: 2rem;
    background: linear-gradient(135deg, #E8F5E9 0%, #F1F8F1 50%, #E8F5E9 100%);
    border: 1px solid #C8DCC8;
    border-radius: 12px;
}
.about-hero h2 {
    color: #1B5E20;
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 700;
    font-size: 1.8rem;
    letter-spacing: -0.02em;
    margin-bottom: 0.25rem;
}
.about-hero .version {
    color: #2E7D32;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    letter-spacing: 0.05em;
    margin-bottom: 1rem;
}
.about-hero p {
    color: #4A6B4A;
    font-size: 1rem;
    line-height: 1.6;
    max-width: 650px;
    margin: 0 auto;
}
.about-card {
    background: #FFFFFF;
    border: 1px solid #C8DCC8;
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1rem;
}
.about-card h3 {
    color: #1B5E20;
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 600;
    font-size: 1.05rem;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.about-card ul {
    list-style: none;
    padding: 0;
    margin: 0;
}
.about-card ul li {
    color: #4A6B4A;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 0.9rem;
    line-height: 1.6;
    padding: 0.3rem 0;
    padding-left: 1.2rem;
    position: relative;
}
.about-card ul li::before {
    content: "\\25B8";
    color: #2E7D32;
    position: absolute;
    left: 0;
}
.about-tech {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.5rem;
}
.tech-badge {
    background: #E8F5E9;
    color: #1B5E20;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    padding: 0.3rem 0.75rem;
    border-radius: 4px;
    border: 1px solid #C8DCC8;
}
.about-footer {
    text-align: center;
    padding: 1.5rem;
    margin-top: 1rem;
    color: #7A9A7A;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    border-top: 1px solid #C8DCC8;
}
</style>
"""


class About(PageBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def render(self):
        super().render()
        st.markdown(ABOUT_CSS, unsafe_allow_html=True)

        # Hero section
        st.markdown(
            """
            <div class="about-hero">
                <h2>FIRA &mdash; Financial Intelligence &amp; Resource Analytics</h2>
                <div class="version">v2.1</div>
                <p>
                    An enterprise-grade financial analytics platform combining interactive resource planning,
                    AI-powered data analysis, and comprehensive OpEx intelligence &mdash; built for finance
                    teams that demand precision.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Feature cards
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(
                """
                <div class="about-card">
                    <h3>Resource Planning</h3>
                    <ul>
                        <li>Interactive demand vs. capacity visualization</li>
                        <li>Priority-based project stacking</li>
                        <li>Per-country capacity and cost controls</li>
                        <li>Real-time gap analysis with FTE tracking</li>
                        <li>Snapshot save/load for scenario comparison</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                """
                <div class="about-card">
                    <h3>AI ChatBot</h3>
                    <ul>
                        <li>Natural language financial queries</li>
                        <li>SQL-powered data retrieval</li>
                        <li>Auto-generated charts and visualizations</li>
                        <li>Executive-quality analysis responses</li>
                        <li>Conversation export and session history</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col2:
            st.markdown(
                """
                <div class="about-card">
                    <h3>Financial Analytics</h3>
                    <ul>
                        <li>Financial trend tracking over time</li>
                        <li>Department rollup and cost center views</li>
                        <li>Resource allocation optimization</li>
                        <li>Geographic and organizational analytics</li>
                        <li>Custom plotting sandbox</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                """
                <div class="about-card">
                    <h3>Data Management</h3>
                    <ul>
                        <li>CSV and XLSX file ingestion</li>
                        <li>Automated data parsing and normalization</li>
                        <li>PostgreSQL backend with SQLite fallback</li>
                        <li>Secure enterprise data handling</li>
                        <li>Export capabilities across all modules</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Tech stack
        st.markdown(
            """
            <div class="about-card">
                <h3>Technology Stack</h3>
                <div class="about-tech">
                    <span class="tech-badge">Python</span>
                    <span class="tech-badge">Streamlit</span>
                    <span class="tech-badge">PostgreSQL</span>
                    <span class="tech-badge">SQLite</span>
                    <span class="tech-badge">Plotly</span>
                    <span class="tech-badge">Pandas</span>
                    <span class="tech-badge">SQLAlchemy</span>
                    <span class="tech-badge">LangChain</span>
                    <span class="tech-badge">OpenAI API</span>
                    <span class="tech-badge">IBM Plex</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Footer
        st.markdown(
            """
            <div class="about-footer">
                FIRA &mdash; Financial Intelligence &amp; Resource Analytics &bull; Built for Enterprise Finance Teams
            </div>
            """,
            unsafe_allow_html=True,
        )
