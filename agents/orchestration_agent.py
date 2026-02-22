import logging
from typing import Optional, Dict, Any

# Import the Router/Gatekeeper
from agents.user_intent_agent import UserIntentAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrchestrationSessionState:
    """
    Maintains the state for the current interaction.
    Simplified to focus on input/output as internal logic (SQL/RAG) is now delegated.
    """
    def __init__(self, user_input: str):
        self.user_input = user_input
        self.formatted_response: Optional[str] = None
        
        # Optional: metadata for debugging or UI display
        self.intent_category: Optional[str] = None
        self.executed_agent: Optional[str] = None

class OrchestrationAgent:
    """
    Top-level Orchestrator for the Opex Data System.
    Replaces the old DVT orchestration logic.
    """
    def __init__(self):
        # The UserIntentAgent handles routing to SQL, Semantic, or Chat agents.
        self.router = UserIntentAgent()

    def run_chain(self, user_input: str) -> OrchestrationSessionState:
        """
        Executes the main logic flow:
        1. Receive Input
        2. Route to appropriate specialized agent via UserIntentAgent
        3. Return state with response
        """
        state = OrchestrationSessionState(user_input)
        
        try:
            logger.info(f"Orchestrating query: {user_input}")
            
            # Delegate the heavy lifting to the Router.
            # route_and_execute() determines the intent and runs the correct sub-agent.
            response_text = self.router.route_and_execute(user_input)
            
            # Store the result
            state.formatted_response = response_text
            
        except Exception as e:
            logger.error(f"Orchestration failed: {e}", exc_info=True)
            state.formatted_response = (
                "I encountered a system error while processing your request. "
                "Please check the logs for details."
            )
            
        return state

    def run_multiturn_chain(self, state: OrchestrationSessionState = None, recursion_limit=0):
        """
        Compatibility method for existing execution frameworks.
        Accepts either a state object or uses the one passed in.
        """
        # If called with just a string (common in some UI frameworks), wrap it
        if isinstance(state, str):
            state = OrchestrationSessionState(state)
        
        # If called with no state (error case), return empty
        if state is None:
            return OrchestrationSessionState("")

        return self.run_chain(state.user_input)

if __name__ == "__main__":
    print("\n=== Initializing Opex Orchestration Agent ===")
    
    orchestrator = OrchestrationSessionState()
    
    # Test Query
    query = "What is the total spend for the Austin site?"
    print(f"User: {query}")
    
    result_state = orchestrator.run_chain(query)
    print(f"Bot:  {result_state.formatted_response}")