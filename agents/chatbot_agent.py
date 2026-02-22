import logging
from agents.utils.agent_utils import AgentUtils

# Configure logging
logger = logging.getLogger(__name__)

class ChatbotAgent:
    """
    Agent responsible for General Chat, Greetings, and Capabilities explanations.
    It acts as the 'Face' of the system when no specific data/search is needed.
    """

    def __init__(self):
        self.utils = AgentUtils()
        
    def run(self, user_query: str) -> str:
        """
        Generates a conversational response based on the user's input.
        """
        logger.info(f"--- General Chat Started: '{user_query}' ---")

        # 1. Quick check for specific "Help" or "Capabilities" keywords
        #    to provide a deterministic, high-quality menu.
        if self._is_help_request(user_query):
            return self._get_capabilities_message()

        # 2. Construct Persona-based Prompt
        system_prompt = (
            "You are the FIRA Financial & Resource Analyst, a professional-grade assistant "
            "for operational expense analysis, resource demand planning, and capacity forecasting.\n\n"

            "**Your expertise covers:**\n"
            "- OpEx financial data: spend analysis, budget vs actual variance, cost center performance\n"
            "- Resource planning: headcount demand, FTE allocation, staffing by project and country\n"
            "- Capacity forecasting: project priority rankings, target capacity, country-level costing\n\n"

            "**Communication guidelines:**\n"
            "1. Maintain a professional, executive-level tone at all times.\n"
            "2. Use precise financial and resource planning terminology.\n"
            "3. If the user greets you, respond warmly and briefly summarize your analytical capabilities.\n"
            "4. If the question is outside your domain (sports, weather, general coding), "
            "politely redirect the conversation to financial or resource planning topics.\n"
            "5. Never fabricate data. If unsure, ask the user to clarify or suggest specific queries they can try.\n"
            "6. Provide sufficiently detailed responses — your audience consists of finance directors, "
            "VPs, and program managers who expect depth and precision.\n\n"

            f"**User Input:** {user_query}\n\n"
            "**Response:**"
        )

        # 3. Generate Response
        try:
            response = self.utils.llm_call(system_prompt)
            return response
        except Exception as e:
            logger.error(f"Chatbot LLM call failed: {e}")
            return "I'm having trouble processing that right now. How else can I assist you with your data?"

    def _is_help_request(self, query: str) -> bool:
        """
        Simple heuristic to detect if the user is asking what the bot can do.
        """
        keywords = ["help", "what can you do", "capabilities", "features", "menu", "assist"]
        q_lower = query.lower()
        return any(k in q_lower for k in keywords)

    def _get_capabilities_message(self) -> str:
        """
        Returns a formatted string of capabilities.
        """
        return (
            "**I can assist you with the following:**\n\n"

            "**OpEx Financial Analytics**\n"
            "- \"What is the total spend for Project X in Q4?\"\n"
            "- \"Compare budget vs actual variance by department for this fiscal year.\"\n"
            "- \"Show the top 5 projects by spend with their department leads.\"\n"
            "- \"What is the HW vs SW cost split by region?\"\n\n"

            "**Resource Demand & Capacity Planning**\n"
            "- \"What is the total headcount demand by project for this month?\"\n"
            "- \"Show FTE allocation by homegroup across all projects.\"\n"
            "- \"What is the resource demand split by country?\"\n"
            "- \"List projects ranked by priority with their target capacity.\"\n"
            "- \"What is the cost per resource by country?\"\n\n"

            "**Knowledge Search (Semantic)**\n"
            "- \"What is the travel reimbursement policy?\"\n"
            "- \"How do I submit a variance report?\"\n"
            "- \"Summarize the FY24 strategic goals.\"\n\n"

            "Ask me anything in plain English — I will generate the appropriate "
            "analysis and present the results with charts and tables."
        )

if __name__ == "__main__":
    print("\n=== Initializing Chatbot Agent ===")
    try:
        bot = ChatbotAgent()
        
        test_inputs = [
            "Hello, who are you?",
            "Can you help me?",
            "What is the capital of France?", # Out of scope test
            "I need to analyze some variance data."
        ]

        print(f"\nRunning {len(test_inputs)} test cases...\n")

        for inp in test_inputs:
            print(f"👤 User: {inp}")
            resp = bot.run(inp)
            print(f"🤖 Bot:  {resp}\n")
            print("-" * 50)

    except Exception as e:
        logger.error(f"Initialization Failed: {e}")