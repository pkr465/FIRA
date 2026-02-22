import streamlit as st
import logging
from typing import Optional

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import Existing Modules
from ui.modules.chatbot import ChatBot
from ui.modules.summary import Summary
from ui.modules.faq import FAQ
from ui.modules.about import About
from ui.modules.chat_history import ChatHistory

# Import New Analytic Modules
from ui.modules.metrics_financial_trends import FinancialTrends
from ui.modules.metrics_dept_rollup import DeptRollup
from ui.modules.metrics_resource_allocation import ResourceAllocation
from ui.modules.metrics_geo_org import GeoOrgMetrics
from ui.modules.plotting_sandbox import SandboxPage

# Import CBN Resource Planner
from ui.modules.cbn_resource_planner import CBNResourcePlanner

# Import Data Management Page
from ui.modules.data_management import DataManagement

# Define Pages
PAGES = {
    "Resource Planner": CBNResourcePlanner(title="FIRA Resource Planner", url="cbn_planner"),
    "Data Mgmt": DataManagement(title="Data Management", url="data_management"),
    "Summary": Summary(title="Project Summary", url="summary"),
    "Financial Trends": FinancialTrends(title="Financial Trends", url="financial_trends"),
    "Resource Alloc": ResourceAllocation(title="Resource Allocation", url="resource_allocation"),
    "Dept Rollup": DeptRollup(title="Dept Rollup", url="department_rollup"),
    "Geo & Org": GeoOrgMetrics(title="Geo & Org Analytics", url="geo_org"),
    "Sandbox": SandboxPage(title="Plotting Sandbox", url="sandbox"),
    "ChatBot": ChatBot(title="Opex Chat", url="chatbot"),
    "FAQ": FAQ(title="FAQ", url="faq"),
    "About": About(title="About", url="about"),
    "History": ChatHistory(title="Chat History (Admin)", url="history"),
}

# Default Page
DEFAULT_PAGE = PAGES["Resource Planner"].url
DEFAULT_PAGE_URL = DEFAULT_PAGE

def canonical(slug: Optional[str]) -> str:
    """Validate and return the canonical slug for a page."""
    if slug is None:
        return DEFAULT_PAGE_URL
    
    # Check if slug matches any page URL
    for page in PAGES.values():
        if slug == page.url:
            return slug
    
    return DEFAULT_PAGE_URL

def main():
    # Must be the first Streamlit command
    st.set_page_config(layout="wide", page_title="FIRA")

    # Inject FIRA theme on every page
    try:
        from ui.streamlit_tools import app_css
        app_css()
    except Exception:
        pass

    # 1. Router Logic
    query_params = st.query_params
    current_page_slug = query_params.get("page", DEFAULT_PAGE_URL)
    
    # Validate slug
    valid_slug = canonical(current_page_slug)
    
    # Find the page object
    current_page = None
    for page in PAGES.values():
        if page.url == valid_slug:
            current_page = page
            break
            
    if not current_page:
        current_page = PAGES["ChatBot"]

    # 2. Sidebar Navigation
    with st.sidebar:
        # FIRA logo
        import os as _os
        _logo_path = _os.path.join(_os.path.dirname(__file__), "fira_logo.svg")
        if _os.path.exists(_logo_path):
            with open(_logo_path) as _f:
                _svg = _f.read()
            st.markdown(
                f'<div style="text-align:center;padding:8px 0 4px;">{_svg}</div>',
                unsafe_allow_html=True,
            )
        st.title("Navigation")
        
        # Iterating through pages to create navigation buttons
        for key, page in PAGES.items():
            # Highlight the active button
            button_type = "primary" if page == current_page else "secondary"
            if st.button(key, use_container_width=True, type=button_type):
                st.query_params["page"] = page.url
                st.rerun()

    # 3. Render Page
    try:
        current_page.render()
    except Exception as e:
        st.error(f"An error occurred rendering the page: {e}")
        logger.exception(e)

if __name__ == "__main__":
    main()