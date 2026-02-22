"""
streamlit_tools.py

Authors : Pavan R, Badri Ramesh
"""

import re
import logging
import streamlit as st
import pandas as pd

logger = logging.getLogger(__name__)


# ================================================================
#  GREENBACK FINANCE THEME — Light Professional Color Scheme
# ================================================================
#
#  Palette (Light Mode):
#    Background page:   #F1F8F1  (light mint)
#    Background card:   #FFFFFF  (white)
#    Surface sidebar:   #E0F0E0  (soft sage)
#    Border:            #C8DCC8  (light green edge)
#    Border accent:     #1B5E20  (deep dollar green)
#    Text primary:      #1A2E1A  (dark forest — high contrast)
#    Text secondary:    #4A6B4A  (muted olive)
#    Heading:           #1B5E20  (deep green)
#    Accent primary:    #2E7D32  (US currency green)
#    Accent bright:     #1B5E20  (darker green for hover)
#    Accent gold:       #8B6914  (dark gold — readable on light)
#    Positive:          #1B5E20  (deep green)
#    Negative:          #C62828  (strong red)
#    Neutral muted:     #7A9A7A  (disabled / placeholder)
# ================================================================

FINANCE_CSS = """
<style>
/* ============================================================
   GREENBACK FINANCE THEME — LIGHT MODE
   ============================================================ */

@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

/* --- CSS Variables --- */
:root {
    --gb-bg-deep:      #F1F8F1;
    --gb-bg-panel:     #FFFFFF;
    --gb-surface:      #E8F5E9;
    --gb-border:       #C8DCC8;
    --gb-border-accent:#2E7D32;
    --gb-text:         #1A2E1A;
    --gb-text-sec:     #4A6B4A;
    --gb-heading:      #1B5E20;
    --gb-accent:       #2E7D32;
    --gb-accent-bright:#1B5E20;
    --gb-gold:         #8B6914;
    --gb-positive:     #1B5E20;
    --gb-negative:     #C62828;
    --gb-muted:        #7A9A7A;
    --gb-radius:       8px;
    --gb-font:         'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --gb-mono:         'IBM Plex Mono', 'SF Mono', 'Fira Code', monospace;
}

/* --- Global Body --- */
html, body, [class*="css"] {
    font-family: var(--gb-font) !important;
    color: var(--gb-text) !important;
    background-color: var(--gb-bg-deep) !important;
    -webkit-font-smoothing: antialiased;
    font-feature-settings: "tnum" on, "lnum" on;
}

.stApp {
    background-color: var(--gb-bg-deep) !important;
}

/* --- Headings --- */
h1, h2, h3, h4, h5, h6,
[data-testid="stHeadingWithActionElements"] {
    font-family: var(--gb-font) !important;
    color: var(--gb-heading) !important;
    font-weight: 700 !important;
    letter-spacing: -0.01em;
}
h1 {
    color: var(--gb-heading) !important;
    -webkit-text-fill-color: var(--gb-heading) !important;
    background: none !important;
    margin-bottom: 0.6em;
}
h2 { border-bottom: 2px solid var(--gb-border-accent); padding-bottom: 6px; }

/* --- Paragraphs & Labels --- */
p, span, label, .stCaption, [data-testid="stCaptionContainer"] {
    color: var(--gb-text-sec) !important;
}

/* --- Sidebar --- */
section[data-testid="stSidebar"] {
    background-color: var(--gb-surface) !important;
    border-right: 1px solid var(--gb-border) !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: var(--gb-heading) !important;
    -webkit-text-fill-color: var(--gb-heading) !important;
    background: none !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background-color: var(--gb-bg-panel) !important;
    border: 1px solid var(--gb-border) !important;
    color: var(--gb-text) !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    border-color: var(--gb-accent) !important;
    background-color: #E8F5E9 !important;
    color: var(--gb-accent) !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"],
section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] {
    background-color: var(--gb-accent) !important;
    color: #fff !important;
    border-color: var(--gb-accent) !important;
}

/* --- Expanders --- */
details, [data-testid="stExpander"] {
    border: 1px solid var(--gb-border) !important;
    border-radius: var(--gb-radius) !important;
    background-color: var(--gb-bg-panel) !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpanderToggleIcon"] {
    color: var(--gb-heading) !important;
}

/* --- Cards / Metric Boxes --- */
[data-testid="stMetric"],
[data-testid="stMetricValue"] {
    font-family: var(--gb-mono) !important;
    color: var(--gb-positive) !important;
    font-weight: 700 !important;
}
[data-testid="stMetricLabel"] {
    color: var(--gb-text-sec) !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 12px !important;
}
[data-testid="stMetricDelta"][data-testid*="positive"] { color: var(--gb-positive) !important; }
[data-testid="stMetricDelta"][data-testid*="negative"] { color: var(--gb-negative) !important; }

/* --- Tables & DataFrames --- */
.stDataFrame, .stTable {
    font-family: var(--gb-mono) !important;
}
table {
    border-collapse: separate !important;
    border-spacing: 0;
    width: 100% !important;
    border: 1px solid var(--gb-border) !important;
    border-radius: var(--gb-radius) !important;
    overflow: hidden !important;
    box-shadow: 0 1px 6px rgba(0,0,0,0.08) !important;
    margin-bottom: 1.5em !important;
    background-color: var(--gb-bg-panel) !important;
}
thead tr th {
    background-color: #E8F5E9 !important;
    color: var(--gb-heading) !important;
    font-family: var(--gb-font) !important;
    font-weight: 700 !important;
    font-size: 12px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    border-bottom: 2px solid var(--gb-border-accent) !important;
    padding: 10px 14px !important;
    text-align: left !important;
}
tbody tr td {
    background-color: var(--gb-bg-panel) !important;
    color: var(--gb-text) !important;
    font-family: var(--gb-mono) !important;
    font-size: 13px !important;
    border-bottom: 1px solid #E0F0E0 !important;
    padding: 8px 14px !important;
}
tbody tr:nth-child(even) td {
    background-color: #F7FCF7 !important;
}
tbody tr:hover td {
    background-color: #E8F5E9 !important;
}
tbody tr:last-child td {
    border-bottom: none !important;
}

/* --- Buttons --- */
div.stButton > button,
button[kind="secondary"] {
    font-family: var(--gb-font) !important;
    border-radius: var(--gb-radius) !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    border: 1px solid var(--gb-border) !important;
    background-color: var(--gb-bg-panel) !important;
    color: var(--gb-accent) !important;
    transition: all 0.2s ease;
    padding: 6px 16px !important;
}
div.stButton > button:hover,
button[kind="secondary"]:hover {
    border-color: var(--gb-accent) !important;
    background-color: #E8F5E9 !important;
    color: var(--gb-accent-bright) !important;
    box-shadow: 0 1px 4px rgba(46,125,50,0.15);
}
button[kind="primary"],
div.stButton > button[data-testid="stBaseButton-primary"] {
    background-color: var(--gb-accent) !important;
    color: #fff !important;
    border-color: var(--gb-accent) !important;
}
button[kind="primary"]:hover {
    background-color: var(--gb-accent-bright) !important;
    box-shadow: 0 2px 8px rgba(27,94,32,0.25);
}

/* --- Inputs / Select / Number --- */
input, select, textarea,
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stSelectbox"] > div > div {
    font-family: var(--gb-mono) !important;
    background-color: var(--gb-bg-panel) !important;
    color: var(--gb-text) !important;
    border: 1px solid var(--gb-border) !important;
    border-radius: var(--gb-radius) !important;
}
input:focus, select:focus, textarea:focus {
    border-color: var(--gb-accent) !important;
    box-shadow: 0 0 0 2px rgba(46,125,50,0.15) !important;
    outline: none !important;
}

/* --- Selectbox dropdowns --- */
[data-testid="stSelectbox"] label {
    color: var(--gb-text-sec) !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    font-size: 11px !important;
    letter-spacing: 0.06em;
}

/* --- Checkboxes & Toggles --- */
[data-testid="stCheckbox"] label span {
    color: var(--gb-text) !important;
}

/* --- Dividers --- */
hr, [data-testid="stDivider"] {
    border: 0 !important;
    border-top: 1px solid var(--gb-border) !important;
    margin-top: 20px;
    margin-bottom: 20px;
}

/* --- Alerts / Info / Success / Error --- */
[data-testid="stAlert"] {
    border-radius: var(--gb-radius) !important;
    font-family: var(--gb-font) !important;
}
.stSuccess, [data-testid="stAlert"][data-type="success"] {
    background-color: #E8F5E9 !important;
    border-left: 4px solid var(--gb-positive) !important;
    color: var(--gb-positive) !important;
}
.stWarning, [data-testid="stAlert"][data-type="warning"] {
    background-color: #FFF8E1 !important;
    border-left: 4px solid #F9A825 !important;
    color: #8B6914 !important;
}
.stError, [data-testid="stAlert"][data-type="error"] {
    background-color: #FFEBEE !important;
    border-left: 4px solid var(--gb-negative) !important;
    color: var(--gb-negative) !important;
}
.stInfo, [data-testid="stAlert"][data-type="info"] {
    background-color: #E3F2FD !important;
    border-left: 4px solid #1565C0 !important;
    color: #1A2E1A !important;
}

/* --- Download buttons --- */
[data-testid="stDownloadButton"] > button {
    background-color: var(--gb-bg-panel) !important;
    border: 1px solid var(--gb-gold) !important;
    color: var(--gb-gold) !important;
}
[data-testid="stDownloadButton"] > button:hover {
    background-color: #FFF8E1 !important;
    color: #6B5010 !important;
}

/* --- File Uploader --- */
[data-testid="stFileUploader"] {
    border: 2px dashed var(--gb-border) !important;
    border-radius: var(--gb-radius) !important;
    background-color: var(--gb-bg-panel) !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: var(--gb-accent) !important;
}

/* --- Spinner --- */
.stSpinner > div > div {
    border-top-color: var(--gb-accent) !important;
}

/* --- Scrollbar (Webkit) --- */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: #F1F8F1; }
::-webkit-scrollbar-thumb { background: #C8DCC8; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #2E7D32; }

/* --- Feedback Widget --- */
.feedback-row {
    background-color: var(--gb-bg-panel);
    border: 1px solid var(--gb-border);
    border-radius: 10px;
    padding: 12px 16px;
    display: flex;
    align-items: center;
    gap: 16px;
    margin-top: 12px;
    margin-bottom: 16px;
}
.feedback-label {
    font-weight: 600;
    font-size: 14px;
    color: var(--gb-heading);
}
.feedback-summary {
    background-color: #E8F5E9;
    border: 1px solid var(--gb-accent);
    border-radius: 20px;
    padding: 4px 12px;
    color: var(--gb-accent);
    font-size: 13px;
    font-weight: 500;
    margin-left: 10px;
    display: inline-block;
}

/* --- Plotly Chart Background Override --- */
.js-plotly-plot .plotly .main-svg { background: transparent !important; }

/* --- Tab styling --- */
[data-testid="stTabs"] [role="tablist"] button {
    color: var(--gb-text-sec) !important;
    border-bottom: 2px solid transparent !important;
}
[data-testid="stTabs"] [role="tablist"] button[aria-selected="true"] {
    color: var(--gb-accent) !important;
    border-bottom-color: var(--gb-accent) !important;
}

</style>
"""


def app_css():
    """Inject the FIRA theme CSS into every page."""
    st.markdown(FINANCE_CSS, unsafe_allow_html=True)


def extract_answer(agent_response):
    """
    Extracts the assistant's answer from a response, for both legacy and orchestrator responses.

    For orchestrator: typically a string is passed (preferred); fallback to dict with 'content'.
    """
    try:
        if isinstance(agent_response, str):
            return agent_response
        if isinstance(agent_response, dict) and "content" in agent_response:
            return agent_response["content"]
        if hasattr(agent_response, "content"):
            return agent_response.content
        if isinstance(agent_response, list) and agent_response:
            # Rare, legacy case: list of messages or dicts
            assistant_msgs = []
            for msg in agent_response:
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    assistant_msgs.append(msg)
                elif hasattr(msg, "role") and msg.role == "assistant":
                    assistant_msgs.append(msg)
            if assistant_msgs:
                last = assistant_msgs[-1]
                if isinstance(last, dict):
                    return last.get("content", "No response.")
                elif hasattr(last, "content"):
                    return last.content
                else:
                    return str(last)
            last = agent_response[-1]
            if isinstance(last, dict):
                return last.get("content", str(last))
            elif hasattr(last, "content"):
                return last.content
            else:
                return str(last)
        elif agent_response is None:
            return "No response."
        else:
            return f"Unknown response type: {type(agent_response)}"
    except Exception as e:
        return f"Error extracting answer: {str(e)}"


# Show how-to-connect instructions only in the About tab
def get_local_ip():
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "localhost"
    finally:
        s.close()
    return ip


# ------------- SIDEBAR --------------
# ------------- IMPROVEMENTS --------------
# ------------- PROMPT SUMMARY --------------
def get_limited_chat_context(history, summary, max_turns=25):
    """
    Returns system+chat message list for LLM:
    - summary goes in a single system message (if any)
    - then up to last `max_turns` user+bot messages
    """
    context = []
    if summary:
        context.append({"role": "system", "content": f"Summary of earlier conversation: {summary}"})
    # Convert (speaker, text) to OpenAI/chat format:
    for speaker, text in history[-max_turns:]:
        if speaker == "You":
            context.append({"role": "user", "content": text})
        else:
            context.append({"role": "assistant", "content": text})
    return context


@st.cache_resource
def process_uploaded_file(uploaded_file):
    # Extract, index, and prepare for question answering. Pre-index uploaded files for faster vector DB integration.
    ...
    # return processed_data


def summarize_chat(messages, prev_summary=""):
    """
    Summarizes a list of (speaker, text) chat tuples using the agent.
    Replace this with a real agent call for ideal results.
    """
    chat_text = "\n".join([f"{speaker}: {text}" for speaker, text in messages])
    # use your agent's summarize capability.
    if not chat_text:
        return prev_summary  # No new content to summarize
    # Simple fallback: concatenate summaries
    return (prev_summary + "\n" + chat_text).strip()[:1000]  # Clip to reasonable length


# ------------- FEEDBACK --------------
def feedback_toggle_sidebar():
    """
    Displays a sidebar toggle for user feedback participation.
    Returns the toggle value (True/False).
    """
    return st.sidebar.toggle(
        "Participate in Feedback? (optional)",
        help=(
            "If enabled, you'll be shown feedback options after each response. All feedback is voluntary. "
            "Feedback and input may be recorded to improve this tool."
        ),
    )


def feedback_widget(response_id, user_message, bot_response):
    if not st.session_state.get("feedback_mode", False):
        return None

    # Use st.columns() with small gaps for each control
    col1, col2, col3, col4, col5 = st.columns([4, 3, 4, 4, 10])

    with col1:
        st.markdown(
            "<span class='feedback-label'>Feedback:</span>",
            unsafe_allow_html=True,
        )
    with col2:
        liked = st.button("👍 Like", key=f"like_{response_id}")
    with col3:
        disliked = st.button("👎 Dislike", key=f"dislike_{response_id}")
    with col4:
        halluc = st.checkbox("🤔 Hallucinated", key=f"halluc_{response_id}")
    with col5:
        # Summary logic
        selection = []
        if liked:
            selection.append("Prefer")
        if disliked:
            selection.append("Don't prefer")
        if halluc:
            selection.append("Hallucination")
        if selection:
            st.markdown(
                f"<span class='feedback-summary'><b>Selected:</b> {' | '.join(selection)}</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<span style='color: #86868B; font-size:13px; margin-left:10px;'>No selection</span>",
                unsafe_allow_html=True,
            )

    if liked or disliked or halluc:
        st.success("Thank you for your feedback!")
        feedback = {
            "user_message": user_message,
            "bot_response": bot_response,
            "liked": liked,
            "disliked": disliked,
            "hallucination": halluc,
            "timestamp": pd.Timestamp.now().isoformat(),
        }
        return feedback
    return None