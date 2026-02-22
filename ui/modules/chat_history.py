import logging
import streamlit as st
from datetime import datetime
from .base import PageBase

# Updated Import Path
from chat.chat_persistence import ChatPersistenceService
from config.config import Config

logger = logging.getLogger(__name__)


class ChatHistory(PageBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.persistence = ChatPersistenceService()
    
    def check_password(self) -> bool:
        """Check if the user has entered the correct password."""
        # Initialize session state for authentication
        if "chat_history_authenticated" not in st.session_state:
            st.session_state.chat_history_authenticated = False
        
        # If already authenticated, return True
        if st.session_state.chat_history_authenticated:
            return True
        
        # Check if password is configured
        if not hasattr(Config, 'ADMIN_HISTORY_PASSWORD') or not Config.ADMIN_HISTORY_PASSWORD:
            # Fallback/Default for development if not set
            st.warning("ADMIN_HISTORY_PASSWORD not set in Config. Defaulting to 'admin'.")
            Config.ADMIN_HISTORY_PASSWORD = "admin"
        
        # Show password input
        st.markdown("### 🔒 Admin Access Required")
        st.markdown("Please enter the admin password to view chat history.")
        
        password = st.text_input("Password", type="password", key="admin_password_input")
        
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("Login", type="primary"):
                if password == Config.ADMIN_HISTORY_PASSWORD:
                    st.session_state.chat_history_authenticated = True
                    st.success("Authentication successful!")
                    st.rerun()
                else:
                    st.error("Incorrect password")
        
        with col2:
            if st.button("Cancel"):
                st.info("Access denied")
        
        return False
    
    def render(self):
        super().render()
        
        # Check authentication
        if not self.check_password():
            return
        
        # Add logout button in the corner
        col1, col2 = st.columns([4, 1])
        with col2:
            if st.button("🚪 Logout"):
                st.session_state.chat_history_authenticated = False
                st.rerun()
        
        st.markdown("## 💬 Chat History Admin Panel")
        st.markdown("---")
        
        # Get recent sessions
        limit = st.slider("Number of sessions to display", min_value=5, max_value=100, value=20, step=5)
        sessions = self.persistence.get_recent_sessions(limit=limit)
        
        if not sessions:
            st.info("No chat sessions found in the database.")
            return
        
        st.markdown(f"### Recent Chat Sessions ({len(sessions)} sessions)")
        
        # Display sessions in a table-like format
        for idx, session in enumerate(sessions):
            with st.expander(
                f"📝 Session {idx + 1}: {session.session_id[:8]}... | "
                f"Created: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')} | "
                f"Updated: {session.updated_at.strftime('%Y-%m-%d %H:%M:%S')}"
            ):
                # Session details
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Full Session ID:** `{session.session_id}`")
                    st.markdown(f"**Created:** {session.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    st.markdown(f"**Last Updated:** {session.updated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                
                with col2:
                    if session.summary:
                        st.markdown(f"**Summary:** {session.summary}")
                    if session.extra:
                        st.markdown(f"**Metadata:** {session.extra}")
                
                # Get messages for this session
                messages = self.persistence.get_session_messages(session.session_id)
                
                if messages:
                    st.markdown(f"**Messages ({len(messages)}):**")
                    
                    # Display messages
                    for msg_idx, message in enumerate(messages):
                        role_emoji = "👤" if message.role == "user" else "🤖"
                        role_color = "#1f77b4" if message.role == "user" else "#2ca02c"
                        
                        # Create a container for each message
                        with st.container():
                            st.markdown(
                                f"<div style='background-color: {role_color}22; padding: 10px; "
                                f"border-radius: 5px; margin: 5px 0;'>"
                                f"<b>{role_emoji} {message.role.capitalize()}</b> "
                                f"<span style='color: #888; font-size: 0.8em;'>"
                                f"({message.timestamp.strftime('%Y-%m-%d %H:%M:%S')})</span>"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                            
                            # Display message content
                            st.markdown(message.content)
                            
                            # Display metadata if present
                            if message.extra:
                                with st.expander("📊 Message Metadata"):
                                    st.json(message.extra)
                else:
                    st.info("No messages in this session.")
                
                # Action buttons
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button(f"📥 Download Session", key=f"download_{session.session_id}"):
                        # Create downloadable content
                        content = f"Session ID: {session.session_id}\n"
                        content += f"Created: {session.created_at}\n"
                        content += f"Updated: {session.updated_at}\n"
                        if session.summary:
                            content += f"Summary: {session.summary}\n"
                        content += "\n" + "="*80 + "\n\n"
                        
                        for message in messages:
                            content += f"[{message.timestamp}] {message.role.upper()}:\n"
                            content += f"{message.content}\n\n"
                        
                        st.download_button(
                            label="Download as Text",
                            data=content,
                            file_name=f"chat_session_{session.session_id[:8]}.txt",
                            mime="text/plain",
                            key=f"download_btn_{session.session_id}"
                        )
                
                with col2:
                    if st.button(f"🗑️ Delete Session", key=f"delete_{session.session_id}", type="secondary"):
                        if st.session_state.get(f"confirm_delete_{session.session_id}", False):
                            # Actually delete
                            if self.persistence.delete_session(session.session_id):
                                st.success(f"Session {session.session_id[:8]}... deleted successfully!")
                                st.rerun()
                            else:
                                st.error("Failed to delete session")
                        else:
                            # Ask for confirmation
                            st.session_state[f"confirm_delete_{session.session_id}"] = True
                            st.warning("Click again to confirm deletion")
                
                with col3:
                    # Reset confirmation state
                    if st.button(f"↩️ Cancel", key=f"cancel_{session.session_id}"):
                        st.session_state[f"confirm_delete_{session.session_id}"] = False
                        st.rerun()
        
        # Statistics section
        st.markdown("---")
        st.markdown("### 📊 Statistics")
        
        total_messages = sum(len(self.persistence.get_session_messages(s.session_id)) for s in sessions)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Sessions", len(sessions))
        with col2:
            st.metric("Total Messages", total_messages)
        with col3:
            avg_messages = total_messages / len(sessions) if sessions else 0
            st.metric("Avg Messages/Session", f"{avg_messages:.1f}")