import os
import streamlit as st
import logging

logger = logging.getLogger(__name__)


def check_credentials(username: str, password: str) -> bool:
    """Validate credentials against .env values."""
    expected_user = os.environ.get("FIRA_USERNAME", "")
    expected_pass = os.environ.get("FIRA_PASSWORD", "")

    if not expected_user or not expected_pass:
        logger.error("FIRA_USERNAME or FIRA_PASSWORD not set in .env")
        return False

    return username == expected_user and password == expected_pass


def login_page():
    """Render the FIRA sign-in page. Returns True if authenticated."""

    if st.session_state.get("authenticated"):
        return True

    # Inject FIRA theme CSS
    try:
        from ui.streamlit_tools import app_css
        app_css()
    except ImportError:
        pass

    # Center the login form
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Logo
    _logo_path = os.path.join(os.path.dirname(__file__), "..", "fira_logo.svg")
    if os.path.exists(_logo_path):
        with open(_logo_path) as f:
            _svg = f.read()
        st.markdown(
            f'<div style="text-align:center;padding:40px 0 10px;">{_svg}</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        "<h2 style='text-align:center;'>Sign In</h2>",
        unsafe_allow_html=True,
    )

    # Use columns to center the form
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)

            if submitted:
                if check_credentials(username, password):
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

    return False
