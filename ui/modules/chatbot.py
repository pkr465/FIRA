"""
FIRA Financial Assistant — Comprehensive Interactive Chat Interface

Features:
  - FIRA-styled message bubbles and professional UI
  - Auto-generated Plotly charts for numerical responses
  - Formatted tables with financial styling
  - Interactive follow-up suggestion buttons
  - Clarification flow with query improvement suggestions
  - Data quality warning banners
  - Query interpretation display ("I understood your question as...")
  - Collapsible SQL viewer
  - Insight analysis cards with LLM-generated trends
  - Error recovery with helpful suggestions
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

/* Interpretation badge */
.interpretation-badge {
    background-color: #E8F0FE;
    border: 1px solid #B3D1FF;
    border-radius: 6px;
    padding: 8px 14px;
    margin-bottom: 10px;
    font-size: 13px;
    color: #1A3A5C;
}
.interpretation-badge strong {
    color: #0D47A1;
}

/* Warning banner */
.dq-warning {
    background-color: #FFF8E1;
    border: 1px solid #FFE082;
    border-left: 3px solid #FFA000;
    border-radius: 6px;
    padding: 8px 14px;
    margin: 8px 0;
    font-size: 12px;
    color: #5D4037;
}

/* Follow-up suggestion */
.followup-card {
    background-color: #F3E5F5;
    border: 1px solid #CE93D8;
    border-radius: 8px;
    padding: 10px 16px;
    margin-top: 12px;
}
.followup-card h5 {
    color: #6A1B9A !important;
    -webkit-text-fill-color: #6A1B9A !important;
    background: none !important;
    font-size: 13px !important;
    margin: 0 0 6px 0 !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

/* Clarification card */
.clarification-card {
    background-color: #FFF3E0;
    border: 1px solid #FFCC02;
    border-left: 3px solid #FF9800;
    border-radius: 8px;
    padding: 14px 18px;
    margin: 10px 0;
}
.clarification-card h4 {
    color: #E65100 !important;
    -webkit-text-fill-color: #E65100 !important;
    background: none !important;
    font-size: 14px !important;
    margin: 0 0 8px 0 !important;
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
            df = pd.read_csv(io.StringIO(markdown_str), sep="|", engine="python")
            df.columns = df.columns.str.strip()
            df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
            df = df.dropna(axis=1, how="all")
            # Drop separator rows (e.g., "---")
            df = df[~df.apply(lambda row: row.astype(str).str.match(r"^[\s\-:]+$").all(), axis=1)]

            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
                return df
        except Exception as e:
            logger.warning(f"Table parsing failed: {e}")
            st.markdown(markdown_str)
        return None

    def _try_auto_chart(self, df: pd.DataFrame, chart_type: str = "bar"):
        """
        Generate a Plotly chart based on the LLM-selected chart_type.
        Supports: bar, grouped_bar, line, pie, area, scatter, heatmap, treemap, waterfall, none.
        Falls back to smart auto-detection if chart_type is unrecognized.
        """
        try:
            import plotly.graph_objects as go
            import plotly.express as px
        except ImportError:
            return

        if df is None or df.empty or len(df) < 2:
            return

        if chart_type == "none":
            return

        # Coerce potential numeric columns
        for col in df.columns:
            if df[col].dtype == object:
                cleaned = df[col].astype(str).str.replace(r"[\$,]", "", regex=True).str.strip()
                numeric_vals = pd.to_numeric(cleaned, errors="coerce")
                if numeric_vals.notna().sum() > len(df) * 0.5:
                    df[col] = numeric_vals

        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if not num_cols:
            return

        label_cols = [c for c in df.columns if c not in num_cols]
        label_col = label_cols[0] if label_cols else None
        if label_col is None and chart_type not in ("heatmap", "scatter"):
            return

        # Shared FIRA styling
        base_layout = dict(
            template="plotly_white",
            paper_bgcolor="#F1F8F1",
            plot_bgcolor="#FFFFFF",
            font=dict(family="IBM Plex Sans", color="#1A2E1A"),
            xaxis=dict(tickfont=dict(color="#4A6B4A"), gridcolor="#E0F0E0"),
            yaxis=dict(tickfont=dict(color="#4A6B4A", family="IBM Plex Mono"), gridcolor="#E0F0E0"),
            margin=dict(l=50, r=20, t=50, b=60),
        )
        colors = ["#2E7D32", "#0D47A1", "#E65100", "#6A1B9A", "#00838F", "#C62828", "#1565C0"]

        fig = None

        # ── PIE CHART ─────────────────────────────────────────────────
        if chart_type == "pie":
            fig = go.Figure(
                go.Pie(
                    labels=df[label_col].astype(str),
                    values=df[num_cols[0]],
                    marker=dict(colors=colors * 5),
                    textinfo="label+percent",
                    textfont=dict(size=12, family="IBM Plex Sans"),
                    hole=0.35,
                )
            )
            fig.update_layout(
                title=dict(text=f"{num_cols[0]} Distribution", font=dict(color="#1B5E20")),
                height=420,
                **{k: v for k, v in base_layout.items() if k not in ("xaxis", "yaxis")},
            )

        # ── LINE CHART ────────────────────────────────────────────────
        elif chart_type == "line":
            fig = go.Figure()
            for i, col in enumerate(num_cols[:5]):
                fig.add_trace(
                    go.Scatter(
                        x=df[label_col].astype(str),
                        y=df[col],
                        mode="lines+markers",
                        name=col,
                        line=dict(color=colors[i % len(colors)], width=2),
                        marker=dict(size=7),
                    )
                )
            fig.update_layout(
                title=dict(text=f"Trend: {', '.join(num_cols[:3])}", font=dict(color="#1B5E20")),
                height=400,
                **base_layout,
            )

        # ── AREA CHART ────────────────────────────────────────────────
        elif chart_type == "area":
            fig = go.Figure()
            for i, col in enumerate(num_cols[:5]):
                fig.add_trace(
                    go.Scatter(
                        x=df[label_col].astype(str),
                        y=df[col],
                        mode="lines",
                        name=col,
                        fill="tonexty" if i > 0 else "tozeroy",
                        line=dict(color=colors[i % len(colors)], width=1),
                    )
                )
            fig.update_layout(
                title=dict(text=f"Cumulative: {', '.join(num_cols[:3])}", font=dict(color="#1B5E20")),
                height=400,
                **base_layout,
            )

        # ── SCATTER CHART ─────────────────────────────────────────────
        elif chart_type == "scatter" and len(num_cols) >= 2:
            fig = go.Figure(
                go.Scatter(
                    x=df[num_cols[0]],
                    y=df[num_cols[1]],
                    mode="markers+text",
                    text=df[label_col].astype(str) if label_col else None,
                    textposition="top center",
                    textfont=dict(size=10, color="#4A6B4A"),
                    marker=dict(
                        size=10,
                        color=df[num_cols[1]],
                        colorscale=[[0, "#C8E6C9"], [1, "#1B5E20"]],
                        showscale=True,
                        colorbar=dict(title=num_cols[1]),
                    ),
                )
            )
            fig.update_layout(
                title=dict(text=f"{num_cols[0]} vs {num_cols[1]}", font=dict(color="#1B5E20")),
                xaxis_title=num_cols[0],
                yaxis_title=num_cols[1],
                height=420,
                **base_layout,
            )

        # ── HEATMAP ──────────────────────────────────────────────────
        elif chart_type == "heatmap" and label_col and len(num_cols) >= 1:
            # Use first label col as rows; if there's a second label col use it as columns
            second_label = label_cols[1] if len(label_cols) >= 2 else None
            if second_label:
                try:
                    pivot = df.pivot_table(
                        index=label_col, columns=second_label,
                        values=num_cols[0], aggfunc="sum",
                    ).fillna(0)
                    fig = go.Figure(
                        go.Heatmap(
                            z=pivot.values,
                            x=pivot.columns.astype(str).tolist(),
                            y=pivot.index.astype(str).tolist(),
                            colorscale=[[0, "#E8F5E9"], [0.5, "#66BB6A"], [1, "#1B5E20"]],
                            texttemplate="%{z:,.0f}",
                            textfont=dict(size=10),
                        )
                    )
                    fig.update_layout(
                        title=dict(text=f"{num_cols[0]} Heatmap", font=dict(color="#1B5E20")),
                        height=max(350, len(pivot) * 30 + 100),
                        **{k: v for k, v in base_layout.items()},
                    )
                except Exception:
                    chart_type = "bar"  # Fallback

        # ── TREEMAP ──────────────────────────────────────────────────
        elif chart_type == "treemap" and label_col:
            try:
                fig = px.treemap(
                    df,
                    path=[label_col],
                    values=num_cols[0],
                    color=num_cols[0],
                    color_continuous_scale=["#C8E6C9", "#66BB6A", "#2E7D32", "#1B5E20"],
                )
                fig.update_layout(
                    title=dict(text=f"{num_cols[0]} by {label_col}", font=dict(color="#1B5E20")),
                    height=450,
                    paper_bgcolor="#F1F8F1",
                    font=dict(family="IBM Plex Sans", color="#1A2E1A"),
                    margin=dict(l=10, r=10, t=50, b=10),
                )
            except Exception:
                chart_type = "bar"  # Fallback

        # ── WATERFALL ────────────────────────────────────────────────
        elif chart_type == "waterfall" and label_col:
            try:
                measures = ["relative"] * len(df)
                if len(df) > 1:
                    measures[-1] = "total"
                fig = go.Figure(
                    go.Waterfall(
                        x=df[label_col].astype(str),
                        y=df[num_cols[0]],
                        measure=measures,
                        connector=dict(line=dict(color="#C8DCC8")),
                        increasing=dict(marker=dict(color="#2E7D32")),
                        decreasing=dict(marker=dict(color="#C62828")),
                        totals=dict(marker=dict(color="#0D47A1")),
                        textposition="outside",
                        text=df[num_cols[0]].apply(lambda v: f"{v:,.0f}" if pd.notna(v) else ""),
                        textfont=dict(size=10, family="IBM Plex Mono"),
                    )
                )
                fig.update_layout(
                    title=dict(text=f"{num_cols[0]} Waterfall", font=dict(color="#1B5E20")),
                    height=400,
                    **base_layout,
                )
            except Exception:
                chart_type = "bar"  # Fallback

        # ── GROUPED BAR ──────────────────────────────────────────────
        elif chart_type == "grouped_bar" and len(num_cols) >= 2:
            fig = go.Figure()
            for i, col in enumerate(num_cols[:5]):
                fig.add_trace(
                    go.Bar(
                        x=df[label_col].astype(str),
                        y=df[col],
                        name=col,
                        marker_color=colors[i % len(colors)],
                    )
                )
            fig.update_layout(
                title=dict(text="Comparative Analysis", font=dict(color="#1B5E20")),
                barmode="group",
                legend=dict(font=dict(color="#1A2E1A", size=11)),
                height=400,
                **base_layout,
            )

        # ── BAR (default) ────────────────────────────────────────────
        if fig is None:
            # Default bar chart — single metric or fallback
            if len(num_cols) == 1 and len(df) <= 25:
                fig = go.Figure(
                    go.Bar(
                        x=df[label_col].astype(str),
                        y=df[num_cols[0]],
                        marker_color="#2E7D32",
                        text=df[num_cols[0]].apply(lambda v: f"{v:,.2f}" if pd.notna(v) else ""),
                        textposition="outside",
                        textfont=dict(color="#1B5E20", size=11, family="IBM Plex Mono"),
                    )
                )
                fig.update_layout(
                    title=dict(text=f"{num_cols[0]} by {label_col}", font=dict(color="#1B5E20")),
                    height=350,
                    **base_layout,
                )
            elif len(num_cols) >= 2 and len(df) <= 30:
                fig = go.Figure()
                for i, col in enumerate(num_cols[:5]):
                    fig.add_trace(
                        go.Bar(
                            x=df[label_col].astype(str),
                            y=df[col],
                            name=col,
                            marker_color=colors[i % len(colors)],
                        )
                    )
                fig.update_layout(
                    title=dict(text="Comparative Analysis", font=dict(color="#1B5E20")),
                    barmode="group",
                    legend=dict(font=dict(color="#1A2E1A", size=11)),
                    height=400,
                    **base_layout,
                )

        if fig is not None:
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
        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)

    # -------------------------------------------------------------------
    # Structured Response Renderer (handles all new agent response types)
    # -------------------------------------------------------------------

    def display_formatted_response(self, response_text):
        """
        Render LLM response with rich financial formatting.
        Handles: structured JSON (success, clarification, error), tables, plain text.
        """
        data = response_text

        # 1. Try to parse JSON
        if isinstance(response_text, str):
            try:
                if response_text.strip().startswith("{"):
                    data = json.loads(response_text)
            except json.JSONDecodeError:
                pass

        # 2. Handle structured responses from agents
        if isinstance(data, dict):
            status = data.get("status", "")

            # ── Clarification needed ──────────────────────────────────
            if status == "clarification_needed":
                self._render_clarification(data)
                return

            # ── Error with suggestions ────────────────────────────────
            if status == "error":
                self._render_error(data)
                return

            # ── Successful SQL response ───────────────────────────────
            if status == "success" or "sql" in data or "results" in data:
                self._render_success_response(data)
                return

            # ── Content wrapper ───────────────────────────────────────
            if "content" in data:
                response_text = data["content"]
            elif "message" in data:
                st.markdown(data["message"])
                if data.get("suggestions"):
                    self._render_suggestion_buttons(data["suggestions"])
                return

        # 3. Standard markdown with table detection + auto-charting
        text = str(response_text)
        parts = re.split(r"(\n\|.*\|\n(?:\|[:\-]+\|(?:\n\|.*\|)+)+)", text)

        for part in parts:
            if not part.strip():
                continue
            if "|" in part and "---" in part and "\n" in part:
                chart_df = self._render_markdown_table(part)
                if chart_df is not None and not chart_df.empty:
                    self._try_auto_chart(chart_df, chart_type="bar")
            else:
                st.markdown(part)

    # -------------------------------------------------------------------
    # Specialized renderers for structured responses
    # -------------------------------------------------------------------

    def _render_success_response(self, data: dict):
        """Render a successful SQL query response with all enrichments."""

        # Query interpretation badge
        interpretation = data.get("query_interpretation", "")
        if interpretation:
            st.markdown(
                f'<div class="interpretation-badge">'
                f'<strong>Interpreted as:</strong> {interpretation}'
                f"</div>",
                unsafe_allow_html=True,
            )

        # Data quality warnings
        dq_warnings = data.get("data_quality_warnings", [])
        for warning in dq_warnings:
            st.markdown(
                f'<div class="dq-warning">{warning}</div>',
                unsafe_allow_html=True,
            )

        # Analysis / Explanation
        explanation = data.get("explanation", "")
        if explanation:
            st.markdown(
                f'<div class="analysis-card"><h4>Analysis & Insights</h4>{explanation}</div>',
                unsafe_allow_html=True,
            )

        # Results (table + chart)
        results = data.get("results")
        chart_df = None
        if results:
            if isinstance(results, str):
                if "No results found" in results or "no rows" in results.lower():
                    st.warning(results)
                elif "|" in results and "---" in results:
                    chart_df = self._render_markdown_table(results)
                else:
                    st.markdown(results)
            elif isinstance(results, list):
                chart_df = pd.DataFrame(results)
                st.dataframe(chart_df, use_container_width=True, hide_index=True)
            else:
                st.json(results)

        # Auto-chart with LLM-selected chart type
        if chart_df is not None and not chart_df.empty:
            chart_type = data.get("chart_type", "bar")
            self._try_auto_chart(chart_df, chart_type=chart_type)

        # SQL in expander
        if "sql" in data:
            with st.expander("View Generated SQL Query", expanded=False):
                st.code(data["sql"], language="sql")

        # Follow-up suggestions
        followups = data.get("followup_suggestions", [])
        if followups:
            self._render_followup_suggestions(followups)

    def _render_clarification(self, data: dict):
        """Render a clarification request with suggestions."""
        message = data.get("message", "I need more information to answer accurately.")
        interpreted = data.get("interpreted_as", "")
        issues = data.get("issues", [])
        questions = data.get("clarifying_questions", [])
        suggestions = data.get("suggestions", [])

        html = '<div class="clarification-card">'
        html += f"<h4>Clarification Needed</h4>"
        html += f"<p>{message}</p>"

        if interpreted:
            html += f"<p><strong>I understood your question as:</strong> {interpreted}</p>"

        if issues:
            html += "<p><strong>Potential issues:</strong></p><ul>"
            for issue in issues:
                html += f"<li>{issue}</li>"
            html += "</ul>"

        if questions:
            html += "<p><strong>Could you clarify:</strong></p><ul>"
            for q in questions:
                html += f"<li>{q}</li>"
            html += "</ul>"

        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)

        # Render suggestion buttons
        if suggestions:
            st.markdown("**Try one of these instead:**")
            self._render_suggestion_buttons(suggestions)

    def _render_error(self, data: dict):
        """Render an error response with recovery suggestions."""
        message = data.get("message", "An error occurred.")
        st.error(message)

        last_sql = data.get("last_sql", "")
        if last_sql:
            with st.expander("View Last Attempted SQL", expanded=False):
                st.code(last_sql, language="sql")

        suggestions = data.get("suggestions", [])
        if suggestions:
            st.markdown("**Suggestions to try:**")
            self._render_suggestion_buttons(suggestions)

    def _render_followup_suggestions(self, followups: list):
        """Render follow-up question buttons."""
        if not followups:
            return

        html = '<div class="followup-card"><h5>Dig Deeper</h5>'
        html += "<p>Continue your analysis with these follow-up questions:</p></div>"
        st.markdown(html, unsafe_allow_html=True)

        cols = st.columns(min(len(followups), 3))
        for i, question in enumerate(followups):
            with cols[i % 3]:
                # Truncate long questions for button display
                display = question[:80] + "..." if len(question) > 80 else question
                if st.button(
                    f"\U0001F50D {display}",
                    key=f"followup_{hash(question)}_{i}",
                    use_container_width=True,
                ):
                    st.session_state.chat_history_chat.append(("You", question))
                    st.session_state.chat_history_chat.append(("Assistant", self.PLACEHOLDER))
                    st.rerun()

    def _render_suggestion_buttons(self, suggestions: list):
        """Render clickable suggestion buttons that feed into chat."""
        if not suggestions:
            return

        cols = st.columns(min(len(suggestions), 3))
        for i, suggestion in enumerate(suggestions):
            with cols[i % 3]:
                display = suggestion[:80] + "..." if len(suggestion) > 80 else suggestion
                if st.button(
                    f"\U0001F4A1 {display}",
                    key=f"suggest_{hash(suggestion)}_{i}",
                    use_container_width=True,
                ):
                    st.session_state.chat_history_chat.append(("You", suggestion))
                    st.session_state.chat_history_chat.append(("Assistant", self.PLACEHOLDER))
                    st.rerun()

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
            f"</div>",
            unsafe_allow_html=True,
        )

        # 2. Welcome Banner
        with st.chat_message("assistant", avatar="\U0001F4B5"):
            st.markdown(
                '<div class="finance-welcome">'
                "<h3>FIRA Financial & Resource Analyst</h3>"
                "<p>I provide detailed, data-driven analysis across <strong>operational expenses</strong>, "
                "<strong>resource demand planning</strong>, <strong>project budgets</strong>, and "
                "<strong>capacity forecasting</strong>. Ask me anything about your financial data or "
                "resource allocations and I will deliver thorough, professional insights with supporting "
                "charts and tables.</p>"
                "<p style='margin-top:8px;font-size:12px;color:#7A9A7A;'>"
                "I'll validate your query, generate SQL, analyze the results for trends and anomalies, "
                "and suggest follow-up questions to deepen your analysis.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

        # 3. Example Query Chips — clickable buttons that send through chat
        with st.expander("Suggested Queries", expanded=False):
            st.caption("**OpEx Financial Analytics**")
            opex_queries = [
                ("Total Spend by Quarter", "What is the total spend (ods_m) for each fiscal quarter?"),
                ("Top 5 Projects", "Show me the top 5 projects by total spend."),
                ("Department Leads", "List all unique department leads with their total managed spend."),
                ("HW vs SW Spend", "Compare total HW vs SW spending across all fiscal years."),
                ("Spend by Country", "What is the total spend split by country (home_dept_region_r1)?"),
                ("Budget vs Actual", "Show budget (tm1_m) vs actual spend (ods_m) by project."),
                ("Quarterly Variance", "Show budget vs actual variance by quarter for the latest fiscal year."),
                ("Top VPs by Spend", "Who are the top 5 VPs by total managed spend?"),
            ]
            cols = st.columns(4)
            for i, (title, query) in enumerate(opex_queries):
                with cols[i % 4]:
                    if st.button(f"\U0001F4B0 {title}", key=f"sq_opex_{i}", use_container_width=True):
                        st.session_state.chat_history_chat.append(("You", query))
                        st.session_state.chat_history_chat.append(("Assistant", self.PLACEHOLDER))
                        st.rerun()

            st.caption("**Resource Planner & Demand**")
            rp_queries = [
                ("Demand by Project", "What is the total demand value by project name?"),
                ("Demand by Country", "Show the total resource demand value split by country."),
                ("FTE by Homegroup", "What is the total FTE allocation for each homegroup?"),
                ("Project Priority", "List all projects ranked by priority with their target capacity."),
                ("Cost by Country", "What is the cost per resource (country_cost) by country?"),
                ("Monthly Demand", "Show the total demand value by month across all projects."),
            ]
            cols = st.columns(3)
            for i, (title, query) in enumerate(rp_queries):
                with cols[i % 3]:
                    if st.button(f"\U0001F4CB {title}", key=f"sq_rp_{i}", use_container_width=True):
                        st.session_state.chat_history_chat.append(("You", query))
                        st.session_state.chat_history_chat.append(("Assistant", self.PLACEHOLDER))
                        st.rerun()

            st.caption("**Man-Month Analysis**")
            mm_queries = [
                ("MM by Project", "Show man-months (ods_mm from MM data) by project."),
                ("Plan vs Actual MM", "Compare planned man-months (tm1_mm) vs actual (ods_mm) from MM data by project."),
                ("MM by Department", "What is the man-month allocation by department lead?"),
            ]
            cols = st.columns(3)
            for i, (title, query) in enumerate(mm_queries):
                with cols[i % 3]:
                    if st.button(f"\U0001F4CA {title}", key=f"sq_mm_{i}", use_container_width=True):
                        st.session_state.chat_history_chat.append(("You", query))
                        st.session_state.chat_history_chat.append(("Assistant", self.PLACEHOLDER))
                        st.rerun()

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
        user_input = st.chat_input("Ask about financial data, budgets, resources, man-months...")
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
                    error_resp = {
                        "status": "error",
                        "message": (
                            "I encountered an error processing your request. "
                            "Please verify the database connection and try again."
                        ),
                        "suggestions": [
                            "Try a simpler query",
                            "Check if data has been ingested",
                            "Verify the database is running",
                        ],
                    }
                    answer = json.dumps(error_resp)

            st.session_state.chat_history_chat[-1] = ("Assistant", answer)
            st.rerun()

        # 9. Footer Controls
        st.markdown("---")
        fc1, fc2, fc3 = st.columns([2, 1, 1])

        with fc1:
            if st.session_state.get("chat_history_chat"):
                chat_export = "\n\n".join(
                    f"{'USER' if s == 'You' else 'ANALYST'}: {t}" for s, t in st.session_state["chat_history_chat"]
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
