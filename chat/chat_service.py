import logging
import uuid
import time
from typing import Optional

# Import Persistence
from chat.chat_persistence import ChatPersistenceService

# Import Orchestrator
from agents.orchestration_agent import OrchestrationAgent, OrchestrationSessionState

logger = logging.getLogger(__name__)

class ChatService:
    """
    High-level service that connects the UI/API to the Opex Orchestrator 
    and handles history persistence.
    """
    
    def __init__(self):
        self.orchestrator = OrchestrationAgent()
        self.persistence = ChatPersistenceService()
        self.session_id: Optional[str] = None

    def start_new_session(self) -> str:
        """Starts a new tracking session."""
        self.session_id = str(uuid.uuid4())
        self.persistence.create_session(self.session_id)
        logger.info(f"Chat Service: Started session {self.session_id}")
        return self.session_id

    def get_session_id(self) -> str:
        """Returns current session ID or creates one."""
        if not self.session_id:
            return self.start_new_session()
        return self.session_id

    def set_session_id(self, session_id: str):
        """Resumes an existing session."""
        self.session_id = session_id

    def ask(self, user_msg: str, persist: bool = True) -> str:
        """
        Main entry point:
        1. Persist User Msg
        2. Run Orchestrator
        3. Persist Bot Response
        4. Return Response
        """
        session_id = self.get_session_id()
        
        # 1. Persist User Message
        if persist:
            self.persistence.save_message(session_id, "user", user_msg)

        try:
            # 2. Execute Logic (Routing -> SQL/RAG/Chat)
            state = self.orchestrator.run_chain(user_msg)
            response_text = state.formatted_response

            # 3. Persist Assistant Response
            if persist:
                self.persistence.save_message(session_id, "assistant", response_text)

            return response_text

        except Exception as e:
            logger.error(f"Chat processing failed: {e}", exc_info=True)
            error_msg = "I'm sorry, I encountered an error processing your request."
            
            if persist:
                self.persistence.save_message(
                    session_id, 
                    "assistant", 
                    error_msg, 
                    extra={"error": str(e)}
                )
            return error_msg

    def get_history(self) -> list:
        """Retrieve history for the current session."""
        if not self.session_id:
            return []
        return self.persistence.get_session_messages(self.session_id)

    def run_cli(self):
        """Simple CLI wrapper for testing."""
        print("--- Opex Chat Service (CLI) ---")
        print("Type 'quit' to exit.")
        self.start_new_session()
        
        while True:
            user_input = input("\nUser> ").strip()
            if user_input.lower() in ["quit", "exit", "q"]:
                break
            if not user_input:
                continue
                
            resp = self.ask(user_input)
            print(f"Bot > {resp}")

if __name__ == "__main__":
    # Test the service
    service = ChatService()
    service.run_cli()