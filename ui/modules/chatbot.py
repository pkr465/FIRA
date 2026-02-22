"""
FIRA Financial Assistant — Chat Interface

Professional finance-themed chatbot with:
  - FIRA-styled message bubbles and UI
  - Auto-generated Plotly charts for numerical responses
  - Formatted tables with financial styling
  - Verbose, analytical response presentation
"""

import logging
import streamlit as st
import json
import io
import pandas as pd
import numpy as np
import re
import uuid

from .base import PageBase

# Updated: Import the Opex ChatService
from chat.chat_service import ChatService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chat-specific CSS overlay (layered on top of the global finance theme)
# ---------------------------------------------------------------------------

CHAT_CSS = """
<style>
/* --- Chat Container --- */
[data-testid="stChatMessage"] {
    border: 1px solid #C8DCC8 !important;
    border-radius: 10px !important;
    margin-bottom: 12px !important;
    padding: 14px 18px !important;
    background-color: #FFFFFF !important;
    transition: border-color 0.2s ease;
}
[data-testid="stChatMessage"]:hover {
    border-color: #2E7D32 !important;
}

/* User messages */
[data-testid="stChatMessage"][data-testid*="user"],
.stChatMessage:has([data-testid="chatAvatarIcon-user"]) {
    background-color: #F7FCF7 !important;
    border-left: 3px solid #2E7D32 !important;
}

/* Assistant messages — gold left accent */
[data-testid="stChatMessage"][data-testid*="assistant"],
.stChatMessage:has([data-testid="chatAvatarIcon-assistant"]) {
    background-color: #FFFFFF !important;
    border-left: 3px solid #8B6914 !important;
}

/* Chat input box */
[data-testid="stChatInput"] {
    border-top: 1px solid #C8DCC8 !important;
    padding-top: 12px !important;
}
[data-testid="stChatInput"] textarea {
    background-color: #FFFFFF !important;
    border: 1px solid #C8DCC8 !important;
    border-radius: 10px !important;
    color: #1A2E1A !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: 14px !important;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: #2E7D32 !important;
    box-shadow: 0 0 0 2px rgba(46,125,50,0.15) !important;
}
[data-testid="stChatInput"] button {
    background-color: #2E7D32 !important;
    color: #fff !important;
    border-radius: 8px !important;
}

/* Welcome banner */
.finance-welcome {
    background: linear-gradient(135deg, #E8F5E9 0%, #F1F8F1 50%, #E8F5E9 100%);
    border: 1px solid #C8DCC8;
    border-left: 4px solid #8B6914;
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 20px;
}
.finance-welcome h3 {
    color: #1B5E20 !important;
    -webkit-text-fill-color: #1B5E20 !important;
    background: none !important;
    margin: 0 0 8px 0 !important;
    font-size: 22px !important;
}
.finance-welcome p {
    color: #4A6B4A !important;
    margin: 0 !important;
    font-size: 14px;
    line-height: 1.6;
}

/* Example query chips */
.query-chip {
    display: inline-block;
    background-color: #FFFFFF;
    border: 1px solid #C8DCC8;
    border-radius: 20px;
    padding: 6px 16px;
    margin: 4px 6px 4px 0;
    color: #1B5E20;
    font-size: 13px;
    font-family: 'IBM Plex Sans', sans-serif;
    cursor: default;
    transition: all 0.2s ease;
}
.query-chip:hover {
    border-color: #2E7D32;
    color: #1B5E20;
    background-color: #E8F5E9;
}
.query-chip .chip-icon {
    color: #8B6914;
    margin-right: 6px;
}

/* Analysis cards inside chat */
.analysis-card {
    background-color: #F7FCF7;
    border: 1px solid #C8DCC8;
    border-radius: 8px;
    padding: 14px 18px;
    margin: 10px 0;
}
.analysis-card h4 {
    color: #1B5E20 !important;
    -webkit-text-fill-color: #1B5E20 !important;
    background: none !important;
    font-size: 15px !important;
    margin: 0 0 8px 0 !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* KPI row */
.kpi-row {
    display: flex;
    gap: 16px;
    margin: 12px 0;
    flex-wrap: wrap;
}
.kpi-box {
    flex: 1;
    min-width: 120px;
    background-color: #FFFFFF;
    border: 1px solid #C8DCC8;
    border-radius: 8px;
    padding: 12px 16px;
    text-align: center;
}
.kpi-box .kpi-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 22px;
    font-weight: 700;
    color: #1B5E20;
}
.kpi-box .kpi-label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #7A9A7A;
    margin-top: 4px;
}

/* Spinner override for chat */
.chat-spinner {
    color: #2E7D32 !important;
}

/* Session info badge */
.session-badge {
    display: inline-block;
    background-color: #E8F5E9;
    border: 1px solid #C8DCC8;
    border-radius: 12px;
    padding: 2px 10px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: #4A6B4A;
}
</style>
"""


class ChatBot(PageBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orchestrator: ChatService = self._get_orchestrator()
        self.PLACEHOLDER = "_analyzing_placeholder_"

    @st.cache_resource
    def _get_orchestrator(_self):
        return ChatService()

    # -------------------------------------------------------------------
    # Response Rendering — Rich Financial Formatting
    # -------------------------------------------------------------------

    def _render_markdown_table(self, markdown_str):
        """Parse a Markdown table into a styled Streamlit dataframe."""
        try:
            df = pd.read_csv(io.StringIO(markdown_str), sep='|', engine='python')
            df.columns = df.columns.str.strip()
            df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
            df = df.dropna(axis=1, how='all')
            # Drop separator rows (e.g., "---")
            df = df[~df.apply(lambda row: row.astype(str).str.match(r'^[\s\-:]+$').all(), axis=1)]

            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as e:
            logger.warning(f"Table parsing failed: {e}")
            st.markdown(markdown_str)

    def _try_auto_chart(self, df: pd.DataFrame):
        """
        Automatically generate a Plotly chart if the dataframe contains
        numerical financial data suitable for visualization.
        """
        try:
            import plotly.graph_objects as go
            import plotly.express as px
        except ImportError:
            return

        if df is None or df.empty or len(df) < 2:
            return

        # Identify numeric columns
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if not num_cols:
            return

        # Identify a label column (first non-numeric)
        label_cols = [c for c in df.columns if c not in num_cols]
        label_col = label_cols[0] if label_cols else None

        if label_col is None:
            return

        # Choose chart type based on data shape
        if len(num_cols) == 1 and len(df) <= 20:
            # Bar chart for single metric
            fig = go.Figure(go.Bar(
                x=df[label_col].astype(str),
                y=df[num_cols[0]],
                marker_color="#2E7D32",
                text=df[num_cols[0]].apply(lambda v: f"{v:,.2f}"),
                textposition="outside",
                textfont=dict(color="#1B5E20", size=11, family="IBM Plex Mono"),
            ))
            fig.update_layout(
                title=dict(text=f"{num_cols[0]} by {label_col}", font=dict(color="#1B5E20")),
                template="plotly_white",
                paper_bgcolor="#F1F8F1",
                plot_bgcolor="#FFFFFF",
                font=dict(family="IBM Plex Sans", color="#1A2E1A"),
                xaxis=dict(tickfont=dict(color="#4A6B4A"), gridcolor="#E0F0E0"),
                yaxis=dict(tickfont=dict(color="#4A6B4A", family="IBM Plex Mono"), gridcolor="#E0F0E0"),
                height=350,
                margin=dict(l=50, r=20, t=50, b=60),
            )
            st.plotly_chart(fig, use_container_width=True)

        elif len(num_cols) >= 2 and len(df) <= 30:
            # Grouped bar for multiple metrics
            fig = go.Figure()
            colors = ["#1B5E20", "#0D47A1", "#E65100", "#6A1B9A", "#00838F"]
            for i, col in enumerate(num_cols[:5]):
                fig.add_trace(go.Bar(
                    x=df[label_col].astype(str),
                    y=df[col],
                    name=col,
                    marker_color=colors[i % len(colors)],
                ))
            fig.update_layout(
                title=dict(text="Comparative Analysis", font=dict(color="#1B5E20")),
                template="plotly_white",
                paper_bgcolor="#F1F8F1",
                plot_bgcolor="#FFFFFF",
                font=dict(family="IBM Plex Sans", color="#1A2E1A"),
                barmode="group",
                xaxis=dict(tickfont=dict(color="#4A6B4A"), gridcolor="#E0F0E0"),
                yaxis=dict(tickfont=dict(color="#4A6B4A", family="IBM Plex Mono"), gridcolor="#E0F0E0"),
                legend=dict(font=dict(color="#1A2E1A", size=11)),
                height=400,
                margin=dict(l=50, r=20, t=50, b=60),
            )
            st.plotly_chart(fig, use_container_width=True)

    def _render_kpis(self, data: dict):
        """Render KPI boxes for summary data."""
        if not data:
            return
        html = '<div class="kpi-row">'
        for label, value in data.items():
            if isinstance(value, (int, float)):
                formatted = f"${value:,.2f}" if abs(value) >= 1 else f"{value:,.4f}"
            else:
                formatted = str(value)
            html += f'''
            <div class="kpi-box">
                <div class="kpi-value">{formatted}</div>
                <div class="kpi-label">{label}</div>
            </div>'''
        html += '</div>'
        st.markdown(html, unsafe_allow_html=True)

    def display_formatted_response(self, response_text):
        """
        Render LLM response with rich financial formatting.
        Handles structured JSON, tables, and plain text.
        Automatically generates charts where data supports it.
        """
        data = response_text

        # 1. Try to parse JSON
        if isinstance(response_text, str):
            try:
                if response_text.strip().startswith("{"):
                    data = json.loads(response_text)
            except json.JSONDecodeError:
                pass

        # 2. Structured Agent Response (SQL/Results)
        if isinstance(data, dict) and ('sql' in data or 'results' in data):
            # Explanation
            if 'explanation' in data:
                st.markdown(
                    f'<div class="analysis-card"><h4>Analysis</h4>{data["explanation"]}</div>',
                    unsafe_allow_html=True,
                )

            # Results
            results = data.get('results')
            chart_df = None
            if results:
                if isinstance(results, str):
                    if "No results found" in results:
                        st.warning(results)
                    elif "|" in results and "---" in results:
                        self._render_markdown_table(results)
                        # Try to parse for charting
                        try:
                            chart_df = pd.read_csv(io.StringIO(results), sep='|', engine='python')
                            chart_df.columns = chart_df.columns.str.strip()
                            chart_df = chart_df.loc[:, ~chart_df.columns.str.contains('^Unnamed')]
                            chart_df = chart_df.dropna(axis=1, how='all')
                            chart_df = chart_df[~chart_df.apply(
                                lambda row: row.astype(str).str.match(r'^[\s\-:]+$').all(), axis=1
                            )]
                        except Exception:
                            chart_df = None
                    else:
                        st.markdown(results)
                elif isinstance(results, list):
                    chart_df = pd.DataFrame(results)
                    st.dataframe(chart_df, use_container_width=True, hide_index=True)
                else:
                    st.json(results)

            # Auto-chart
            if chart_df is not None and not chart_df.empty:
                self._try_auto_chart(chart_df)

            # SQL in expander
            if 'sql' in data:
                with st.expander("View Generated SQL Query", expanded=False):
                    st.code(data['sql'], language='sql')
            return

        # 3. Content wrapper
        if isinstance(data, dict) and "content" in data:
            response_text = data["content"]

        # 4. Standard markdown with table detection + auto-charting
        text = str(response_text)
        parts = re.split(r'(\n\|.*\|\n(?:\|[:\-]+\|(?:\n\|.*\|)+)+)', text)

        for part in parts:
            if not part.strip():
                continue
            if "|" in part and "---" in part and "\n" in part:
                self._render_markdown_table(part)
                # Try auto-chart on detected tables
                try:
                    chart_df = pd.read_csv(io.StringIO(part), sep='|', engine='python')
                    chart_df.columns = chart_df.columns.str.strip()
                    chart_df = chart_df.loc[:, ~chart_df.columns.str.contains('^Unnamed')]
                    chart_df = chart_df.dropna(axis=1, how='all')
                    chart_df = chart_df[~chart_df.apply(
                        lambda row: row.astype(str).str.match(r'^[\s\-:]+$').all(), axis=1
                    )]
                    if not chart_df.empty:
                        self._try_auto_chart(chart_df)
                except Exception:
                    pass
            else:
                st.markdown(part)

    # -------------------------------------------------------------------
    # Main Render
    # -------------------------------------------------------------------

    def render(self):
        super().render()

        # Inject chat-specific CSS
        st.markdown(CHAT_CSS, unsafe_allow_html=True)

        # 1. Session Management
        if "chat_session_id" not in st.session_state:
            st.session_state.chat_session_id = str(uuid.uuid4())
            logger.info(f"Created new chat session: {st.session_state.chat_session_id}")

        self.orchestrator.set_session_id(st.session_state.chat_session_id)

        # Session badge (top-right)
        st.markdown(
            f'<div style="text-align:right; margin-bottom:6px;">'
            f'<span class="session-badge">Session {st.session_state.chat_session_id[:8]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # 2. Welcome Banner
        with st.chat_message("assistant", avatar="\U0001F4B5"):
            st.markdown(
                '<div class="finance-welcome">'
                '<h3>FIRA Financial & Resource Analyst</h3>'
                '<p>I provide detailed, data-driven analysis across <strong>operational expenses</strong>, '
                '<strong>resource demand planning</strong>, <strong>project budgets</strong>, and '
                '<strong>capacity forecasting</strong>. Ask me anything about your financial data or '
                'resource allocations and I will deliver thorough, professional insights with supporting '
                'charts and tables.</p>'
                '</div>',
                unsafe_allow_html=True,
            )

        # 3. Example Query Chips
        with st.expander("Suggested Queries", expanded=False):
            st.caption("**OpEx Financial Analytics**")
            opex_queries = [
                ("\U0001F4B0", "Total Spend", "What is the total spend across all cost centers in the latest quarter?"),
                ("\U0001F4CA", "Project Breakdown", "Show me a detailed budget breakdown for the top 5 projects by spend."),
                ("\U0001F465", "Department Leads", "List all unique department leads with their total managed budget."),
                ("\U0001F4C8", "Trend Analysis", "Compare HW vs SW spending trends across the last 4 quarters."),
                ("\U0001F30D", "Geo Analysis", "What is the resource spend split by country?"),
                ("\U0001F6A8", "Variance Report", "Show budget vs actual variance for the current fiscal year."),
            ]
            chips_html = ""
            for icon, title, prompt in opex_queries:
                chips_html += (
                    f'<span class="query-chip">'
                    f'<span class="chip-icon">{icon}</span>'
                    f'<strong>{title}:</strong> {prompt}'
                    f'</span>'
                )
            st.markdown(chips_html, unsafe_allow_html=True)

            st.caption("**Resource Planner & Demand**")
            rp_queries = [
                ("\U0001F4CB", "Headcount Demand", "What is the total headcount demand by project for the current month?"),
                ("\U0001F3E2", "Team Capacity", "Show me the FTE allocation for each homegroup across all projects."),
                ("\U0001F30E", "Country Staffing", "What is the resource demand split by country?"),
                ("\U0001F3AF", "Priority Ranking", "List all projects ranked by priority with their target capacity."),
                ("\U0001F4B5", "Country Cost", "What is the cost per resource by country for the top 5 projects?"),
                ("\U0001F4C5", "Monthly Trend", "Show me the monthly demand trend for the last 6 months by project."),
            ]
            chips_html = ""
            for icon, title, prompt in rp_queries:
                chips_html += (
                    f'<span class="query-chip">'
                    f'<span class="chip-icon">{icon}</span>'
                    f'<strong>{title}:</strong> {prompt}'
                    f'</span>'
                )
            st.markdown(chips_html, unsafe_allow_html=True)

        # 4. History Initialization
        if "chat_history_chat" not in st.session_state:
            st.session_state.chat_history_chat = []
        if "chat_history_chat_summary" not in st.session_state:
            st.session_state.chat_history_chat_summary = ""

        # 5. Render Chat History
        for idx, (speaker, text) in enumerate(st.session_state.chat_history_chat):
            role = "user" if speaker == "You" else "assistant"
            avatar = "\U0001F464" if role == "user" else "\U0001F4B5"

            with st.chat_message(role, avatar=avatar):
                if role == "assistant":
                    self.display_formatted_response(text)
                else:
                    st.markdown(text)

                # Feedback Widget
                if role == "assistant":
                    try:
                        from ui.streamlit_tools import feedback_widget
                        user_msg = ""
                        if idx > 0 and st.session_state.chat_history_chat[idx - 1][0] == "You":
                            user_msg = st.session_state.chat_history_chat[idx - 1][1]
                        feedback = feedback_widget(idx, user_msg, text)
                        if feedback:
                            st.session_state.setdefault("all_feedback", []).append(feedback)
                    except ImportError:
                        pass

        # 6. Summarization Logic
        max_turns = 25
        history = st.session_state.chat_history_chat
        if len(history) > max_turns:
            try:
                from ui.streamlit_tools import summarize_chat
                old_messages = history[:-max_turns]
                prev_summary = st.session_state.chat_history_chat_summary
                new_summary = summarize_chat(old_messages, prev_summary)
                st.session_state.chat_history_chat_summary = new_summary
            except ImportError:
                pass
            st.session_state.chat_history_chat = history[-max_turns:]

        # 7. Input
        user_input = st.chat_input("Ask about financial data, budgets, resources...")
        if user_input:
            st.session_state.chat_history_chat.append(("You", user_input))
            st.session_state.chat_history_chat.append(("Assistant", self.PLACEHOLDER))
            st.rerun()

        # 8. Response Generation
        if (
            st.session_state.chat_history_chat
            and st.session_state.chat_history_chat[-1] == ("Assistant", self.PLACEHOLDER)
        ):
            user_message = st.session_state.chat_history_chat[-2][1]

            with st.spinner("Analyzing financial data..."):
                try:
                    answer = self.orchestrator.ask(user_message)
                except Exception as e:
                    st.error(f"Error: {e}")
                    logger.exception(e)
                    answer = (
                        "I encountered an error processing your request. "
                        "Please verify the database connection and try again."
                    )

            st.session_state.chat_history_chat[-1] = ("Assistant", answer)
            st.rerun()

        # 9. Footer Controls
        st.markdown("---")
        fc1, fc2, fc3 = st.columns([2, 1, 1])

        with fc1:
            if st.session_state.get("chat_history_chat"):
                chat_export = "\n\n".join(
                    f"{'USER' if s == 'You' else 'ANALYST'}: {t}"
                    for s, t in st.session_state["chat_history_chat"]
                )
                st.download_button(
                    "Export Conversation",
                    chat_export,
                    file_name="financial_analysis_chat.txt",
                    mime="text/plain",
                )

        with fc2:
            if st.button("New Session", key="new_session"):
                st.session_state.chat_session_id = str(uuid.uuid4())
                st.session_state.chat_history_chat = []
                st.session_state.chat_history_chat_summary = ""
                st.rerun()

        with fc3:
            with st.expander("Session Details"):
                st.markdown(
                    f'<span class="session-badge">{st.session_state.chat_session_id}</span>',
                    unsafe_allow_html=True,
                )
                msg_count = len(st.session_state.get("chat_history_chat", []))
                st.caption(f"{msg_count} messages in this session")
