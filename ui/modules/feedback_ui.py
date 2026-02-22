"""
ui/modules/feedback_ui.py

Feedback email functionality.
Allows users to submit general feedback about the application via a modal dialog.
"""

import streamlit as st
import logging
import time
from datetime import datetime
from config.config import Config
from qgenie_sdk_tools.utils.email_util import EmailUtil

logger = logging.getLogger(__name__)


@st.dialog("💬 Send Feedback", width="medium")
def send_feedback():
    logger.info("Rendering feedback dialog")

    st.markdown("We'd love to hear your thoughts about the Dashboard!")

    # Create form for feedback
    with st.form("feedback_form", clear_on_submit=True, enter_to_submit=False):
        feedback_content = st.text_area(
            f"Tell us what you think, any features you'd like to see, "
            f"or any problems you've encountered.",
            placeholder="Please share your thoughts, suggestions, or report any issues...",
            height=250,
        )

        email_address = st.text_input(
            "Your Qualcomm ID (optional):",
            placeholder="qualname",
            help="Provide your Qualcomm ID if you'd like us to respond to your feedback.",
        )

        col1, col2 = st.columns([1, 1])

        with col1:
            submit_feedback = st.form_submit_button(
                "Send Feedback", type="primary", use_container_width=True
            )

        with col2:
            cancel_feedback = st.form_submit_button("Cancel", use_container_width=True)

        if submit_feedback:
            if feedback_content.strip():
                if send_feedback_email(feedback_content, email_address):
                    st.success("Thank you for your feedback! We appreciate your input.")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(
                        "Sorry, there was an issue sending your feedback. Please try again later."
                    )
            else:
                st.warning("Please enter some feedback before submitting.")

        if cancel_feedback:
            st.rerun()


def send_feedback_email(feedback_content: str, user_email: str = "") -> bool:
    try:
        # Ensure Config has the email ID, or fallback
        recipients = getattr(Config, 'FEEDBACK_EMAIL_ID', 'pavanr@qti.qualcomm.com')
        
        if not recipients:
            logger.warning("No EMAIL_ID configured for feedback emails")
            return False

        # Prepare email content
        subject = "Opex Dashboard Feedback"

        # Create HTML content for the feedback email
        user_email_section = (
            f"<p><strong>User ID:</strong> {user_email}</p>"
            if user_email.strip()
            else "<p><em>No user ID provided</em></p>"
        )
        feedback_html = feedback_content.replace("\n", "<br>")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

        html_content = f"""
        <html>
        <body>
            <h2>Dashboard Feedback</h2>
            <p><strong>Feedback received:</strong></p>
            <div style="background-color: #f5f5f5; padding: 15px; border-left: 4px solid #007bff; margin: 10px 0;">
                {feedback_html}
            </div>
            
            {user_email_section}
            
            <p><strong>Timestamp:</strong> {timestamp}</p>
            
            <hr>
            <p style="font-size: 12px; color: #666;">
                This feedback was submitted through the Opex Dashboard feedback form.
            </p>
        </body>
        </html>
        """

        # Send email using EmailUtil
        logger.info(f"Sending feedback email to {recipients}")
        email_util = EmailUtil()
        content_array = [{"type": "html", "value": html_content}]
        email_util.send_email(recipients, subject, content_array)

        logger.info("Feedback email sent successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to send feedback email: {e}")
        return False