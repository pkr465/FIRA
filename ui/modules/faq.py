import streamlit as st
from .base import PageBase


FAQ_CSS = """
<style>
.faq-container {
    max-width: 900px;
    margin: 0 auto;
    padding: 0 1rem;
}
.faq-header {
    text-align: center;
    margin-bottom: 2rem;
}
.faq-header h2 {
    color: #1B5E20;
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 700;
    letter-spacing: -0.02em;
}
.faq-header p {
    color: #4A6B4A;
    font-size: 0.95rem;
}
.faq-item {
    background: #FFFFFF;
    border: 1px solid #C8DCC8;
    border-left: 4px solid #2E7D32;
    border-radius: 8px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
    transition: border-color 0.2s;
}
.faq-item:hover {
    border-left-color: #8B6914;
}
.faq-question {
    color: #1A2E1A;
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 600;
    font-size: 1.05rem;
    margin-bottom: 0.5rem;
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
}
.faq-question .icon {
    color: #8B6914;
    flex-shrink: 0;
}
.faq-answer {
    color: #4A6B4A;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 0.93rem;
    line-height: 1.65;
    padding-left: 1.75rem;
}
.faq-category {
    color: #1B5E20;
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 600;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 2rem 0 0.75rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #C8DCC8;
}
.faq-search-wrapper {
    margin-bottom: 1.5rem;
}
</style>
"""

FAQS = {
    "Getting Started": [
        (
            "How do I upload financial data?",
            "Navigate to the Resource Planner page. If no data is loaded, you'll see an upload section "
            "where you can drag-and-drop or browse for .xlsx or .csv files. The system supports BPAFG "
            "demand files and Priority Template files. Once uploaded, data is automatically parsed and "
            "stored in the database for analysis."
        ),
        (
            "What data formats are supported?",
            "The platform supports both CSV (.csv) and Excel (.xlsx) file formats. For demand data, "
            "upload files following the BPAFG format with resource details and monthly demand columns. "
            "For priority data, upload files following the Priority Template format with project rankings, "
            "capacity targets, and cost data."
        ),
        (
            "How do I navigate between pages?",
            "Use the sidebar navigation on the left. Click any page name to switch views. The currently "
            "active page is highlighted with a primary-colored button. Pages include the Resource Planner, "
            "Financial Trends, Resource Allocation, Department Rollup, Geo & Org Analytics, the AI ChatBot, "
            "and more."
        ),
    ],
    "Resource Planner": [
        (
            "How does the Mountain Chart work?",
            "The Mountain Chart (stacked area chart) displays resource demand over time, stacked by project "
            "in priority order. A gold capacity line shows available FTE capacity. Red markers indicate months "
            "where demand exceeds capacity (gaps). Use the Y-axis and X-axis controls to adjust the view, "
            "and toggle gap markers on or off."
        ),
        (
            "Can I reorder project priorities?",
            "Yes. In the Project Order panel, use the arrow buttons to move projects up or down in the "
            "priority stack. The chart and allocation table update in real-time to reflect the new ordering. "
            "Projects at the top of the list receive allocation priority first."
        ),
        (
            "How do capacity and cost adjustments work?",
            "The Capacity panel lets you set FTE capacity per country with optional monthly granularity. "
            "The Cost panel lets you set cost multipliers per country (e.g., different billing rates). "
            "Toggle between Blended and Per-Country cost modes to see how costs change across your portfolio."
        ),
    ],
    "AI ChatBot": [
        (
            "What can I ask the ChatBot?",
            "The AI ChatBot can answer questions about your financial data, including total spend analysis, "
            "project-level breakdowns, resource utilization, trend analysis, and more. Ask natural language "
            "questions like 'What are the top 5 projects by cost?' or 'Show me demand trends for India.'"
        ),
        (
            "Does the ChatBot generate charts?",
            "Yes. When the ChatBot returns data with numerical values, it automatically generates "
            "interactive Plotly charts alongside the tabular data. The system detects chart-worthy responses "
            "and renders bar charts, grouped bar charts, or other appropriate visualizations."
        ),
        (
            "How do I start a new chat session?",
            "Click the 'New Session' button in the ChatBot footer area. This clears the current conversation "
            "and starts fresh. Your previous sessions are preserved and can be viewed on the Chat History page."
        ),
    ],
    "Data & Security": [
        (
            "Where is my data stored?",
            "Financial data is stored in a PostgreSQL database (or SQLite fallback for local development). "
            "All data remains within your organization's infrastructure. No data is sent to external services "
            "except for AI query processing through the configured LLM endpoint."
        ),
        (
            "Can I export data from the platform?",
            "Yes. The Resource Planner includes a 'Download CSV' option that exports the current allocation "
            "table with all applied filters and adjustments. The ChatBot also offers an 'Export Conversation' "
            "feature to save your analysis discussions."
        ),
    ],
}


class FAQ(PageBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def render(self):
        super().render()
        st.markdown(FAQ_CSS, unsafe_allow_html=True)

        st.markdown(
            """
            <div class="faq-header">
                <h2>Frequently Asked Questions</h2>
                <p>Find answers to common questions about FIRA — Financial Intelligence &amp; Resource Analytics</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Search
        st.markdown('<div class="faq-search-wrapper">', unsafe_allow_html=True)
        query = st.text_input(
            "Search FAQs",
            placeholder="Type to filter questions...",
            label_visibility="collapsed",
        )
        st.markdown("</div>", unsafe_allow_html=True)

        # Render FAQ sections
        results_found = False
        for category, items in FAQS.items():
            filtered = [
                (q, a) for q, a in items
                if not query or query.lower() in q.lower() or query.lower() in a.lower()
            ]
            if not filtered:
                continue
            results_found = True

            st.markdown(
                f'<div class="faq-category">{category}</div>',
                unsafe_allow_html=True,
            )
            for q, a in filtered:
                st.markdown(
                    f"""
                    <div class="faq-item">
                        <div class="faq-question">
                            <span class="icon">Q</span> {q}
                        </div>
                        <div class="faq-answer">{a}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        if not results_found and query:
            st.markdown(
                """
                <div style="text-align:center; padding:2rem; color:#4A6B4A;">
                    No FAQs match your search. Try different keywords or
                    ask the <strong>AI ChatBot</strong> for help.
                </div>
                """,
                unsafe_allow_html=True,
            )
