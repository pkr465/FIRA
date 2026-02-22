import logging
from typing import Optional, List, Dict
from datetime import datetime, timezone
from sqlalchemy import (
    select, 
    delete,
    Integer, 
    String, 
    Text, 
    DateTime, 
    JSON, 
    ForeignKeyConstraint, 
    Index,
    desc
)
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy.exc import IntegrityError

# Import the Database Singleton
from utils.models.database import OpexDB

logger = logging.getLogger(__name__)

Base = declarative_base()

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("idx_chat_sessions_session_id", "session_id", unique=True),
        Index("idx_chat_sessions_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc)
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        ForeignKeyConstraint(["session_id"], ["chat_sessions.session_id"], ondelete="CASCADE"),
        Index("idx_chat_messages_session_timestamp", "session_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    extra: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)

class ChatPersistenceService:
    def __init__(self):
        self.db = OpexDB
        self._ensure_tables_exist()
    
    def _ensure_tables_exist(self):
        try:
            Base.metadata.create_all(bind=self.db.engine)
        except Exception as e:
            logger.error(f"Failed to initialize chat tables: {e}")

    def create_session(self, session_id: str, extra: Optional[Dict] = None) -> Optional[ChatSession]:
        try:
            session = ChatSession(session_id=session_id, extra=extra)
            with self.db.SessionLocal() as db_session:
                db_session.add(session)
                db_session.commit()
                return session
        except IntegrityError:
            return self.get_session(session_id)
        except Exception as e:
            logger.error(f"Error creating session {session_id}: {e}")
            return None

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        try:
            with self.db.SessionLocal() as db_session:
                return db_session.execute(
                    select(ChatSession).where(ChatSession.session_id == session_id)
                ).scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error retrieving session {session_id}: {e}")
            return None

    def save_message(self, session_id: str, role: str, content: str, extra: Optional[Dict] = None):
        try:
            if not self.get_session(session_id):
                self.create_session(session_id)

            with self.db.SessionLocal() as db_session:
                msg = ChatMessage(
                    session_id=session_id,
                    role=role,
                    content=str(content),
                    extra=extra
                )
                db_session.add(msg)
                
                chat_session = db_session.execute(
                    select(ChatSession).where(ChatSession.session_id == session_id)
                ).scalar_one()
                chat_session.updated_at = datetime.now(timezone.utc)
                
                db_session.commit()
        except Exception as e:
            logger.error(f"Failed to save message: {e}")

    def get_session_messages(self, session_id: str, limit: int = 50) -> List[ChatMessage]:
        """Returns actual ChatMessage objects for admin view."""
        try:
            with self.db.SessionLocal() as db_session:
                return db_session.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.timestamp.asc())
                    .limit(limit)
                ).scalars().all()
        except Exception as e:
            logger.error(f"Error fetching messages: {e}")
            return []

    # --- NEW METHODS FOR ADMIN PANEL ---

    def get_recent_sessions(self, limit: int = 20) -> List[ChatSession]:
        """Fetch recent chat sessions ordered by updated_at."""
        try:
            with self.db.SessionLocal() as db_session:
                return db_session.execute(
                    select(ChatSession)
                    .order_by(desc(ChatSession.updated_at))
                    .limit(limit)
                ).scalars().all()
        except Exception as e:
            logger.error(f"Error fetching recent sessions: {e}")
            return []

    def delete_session(self, session_id: str) -> bool:
        """Deletes a session and its messages."""
        try:
            with self.db.SessionLocal() as db_session:
                # Messages are deleted via CASCADE, but we can be explicit if needed
                db_session.execute(delete(ChatSession).where(ChatSession.session_id == session_id))
                db_session.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            return False