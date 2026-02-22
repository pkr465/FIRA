import streamlit as st
from typing import Literal, Optional


class PageBase:
    def __init__(
        self,
        title: str,
        url: str,
        icon: str = "::",
        layout: Literal["centered", "wide"] = "wide",
        initial_sidebar_state: Literal["expanded", "collapsed", "auto"] = "expanded",
    ):
        self.title = title
        self.icon = icon
        self.layout: Literal["centered", "wide"] = layout
        self.initial_sidebar_state: Literal["expanded", "collapsed", "auto"] = initial_sidebar_state
        self.url = url

    def render(self):
        # Note: set_page_config is called once in streamlit_app.py main().
        # Avoid calling it again here to prevent Streamlit errors.
        # Instead, just update query params and inject theme.
        st.query_params.clear()
        if self.url:
            st.query_params["page"] = self.url

        # Inject FIRA theme CSS
        try:
            from ui.streamlit_tools import app_css
            app_css()
        except ImportError:
            pass

        st.markdown(
            f"<h1 style='text-align:center; margin-top: -20px;'>{self.title}</h1>",
            unsafe_allow_html=True,
        )