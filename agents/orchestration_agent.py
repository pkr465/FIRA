"""
FIRA Orchestration Agent — Top-level query router

Delegates to UserIntentAgent which routes to SQL, Semantic, or Chat agents.
Handles both string and structured dict responses from agents.
"""

import json
import logging
from typing import Optional, Dict, Any

from agents.user_intent_agent import UserIntentAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrchestrationSessionState:
    """
    Maintains the state for the current interaction.
    Supports both string and structured (dict) responses.
    """
    def __init__(self, user_input: str):
        self.user_input = user_input
        self.formatted_response: Optional[str] = None

        # Metadata
        self.intent_category: Optional[str] = None
        self.executed_agent: Optional[str] = None


class OrchestrationAgent:
    """
    Top-level Orchestrator for the FIRA system.
    Routes queries via UserIntentAgent and serializes structured responses.
    """
    def __init__(self):
        self.router = UserIntentAgent()

    def run_chain(self, user_input: str) -> OrchestrationSessionState:
        """
        Executes the main logic flow:
        1. Receive Input
        2. Route to appropriate agent via UserIntentAgent
        3. Serialize response (dict → JSON string for UI parsing)
        4. Return state with response
        """
        state = OrchestrationSessionState(user_input)

        try:
            logger.info(f"Orchestrating query: {user_input}")

            result = self.router.route_and_execute(user_input)

            # If result is a dict (from SQL agent), serialize it as JSON
            # so the UI can parse and render structured components
            if isinstance(result, dict):
                state.formatted_response = json.dumps(result, default=str)
            else:
                state.formatted_response = str(result) if result else ""

        except Exception as e:
            logger.error(f"Orchestration failed: {e}", exc_info=True)
            # Return a structured error that the UI can render nicely
            error_response = {
                "status": "error",
                "message": "I encountered a system error while processing your request. Please check the logs for details.",
                "suggestions": [
                    "Try a simpler query like 'total spend by project'",
                    "Check if the database connection is active",
                    "Verify data has been ingested",
                ],
            }
            state.formatted_response = json.dumps(error_response)

        return state

    def run_multiturn_chain(self, state: OrchestrationSessionState = None, recursion_limit=0):
        """Compatibility method for existing execution frameworks."""
        if isinstance(state, str):
            state = OrchestrationSessionState(state)
        if state is None:
            return OrchestrationSessionState("")
        return self.run_chain(state.user_input)


if __name__ == "__main__":
    print("\n=== Initializing FIRA Orchestration Agent ===")
    orchestrator = OrchestrationAgent()

    query = "What is the total spend for the Austin site?"
    print(f"User: {query}")

    result_state = orchestrator.run_chain(query)
    print(f"Bot:  {result_state.formatted_response}")
