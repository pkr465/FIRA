# agent_utils.py

from __future__ import annotations
import json
import uuid
import yaml
import time
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any

from rich.pretty import pprint
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_core.messages import HumanMessage
from qgenie.integrations.langchain import QGenieChat
from qgenie.exceptions import QGenieAPIStatusException

# --- Imports ---
from config.config import Config
from db.setup_db import DatabaseSetupManager
from db.vector_retriever import VectorRetriever
from db.embedding_client import EmbeddingClient
# Import the configuration loader
from config.schema_config import SCHEMA_CONFIG

# Configure Logging
logger = logging.getLogger(__name__)

class AgentUtils:
    def __init__(self, config_path="config/config.yaml", schema_path="config/schema.yaml"):
        """
        Initializes the Agent Tools with Database, Schema, and Embedding configurations.
        """
        self.config_path = config_path
        self.schema_path = schema_path
        
        # 1. Initialize Model Name (Single Source of Truth)
        # Defaults to "qgenie-std-3.0" if Config.REASONING_MODEL_NAME is None/Empty
        self.model_name = Config.REASONING_MODEL_NAME or "qgenie-std-3.0"
        
        # 2. Load Schema
        self.schema_config = self._load_yaml(schema_path)

        # 3. Setup Database Connection
        self.db_manager = DatabaseSetupManager(config_path=config_path)
        self.connection_string = self.db_manager._get_connection_string()

        # 4. Initialize Embeddings
        self.embed_client = EmbeddingClient()
        self.embedding_function = self.embed_client.get_embedding_function()

        # 5. Initialize Retriever
        self.retriever = VectorRetriever(
            connection_string=self.connection_string,
            embedding_client=self.embedding_function,
            schema_config=self.schema_config
        )

        logger.info(f"✅ AgentUtils initialized. Model: {self.model_name}")

    @staticmethod
    def _load_yaml(path: str) -> dict:
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load YAML from {path}: {e}")
            return {}

    @staticmethod
    def get_repo_root() -> Path:
        return Path(__file__).resolve().parent.parent

    @staticmethod
    def is_uuid(value: str) -> bool:
        try:
            uuid.UUID(str(value))
            return True
        except (ValueError, TypeError, AttributeError):
            return False

    def _map_criteria_to_schema(self, criteria: dict) -> dict:
        """
        Maps generic LLM extracted keys to actual Database Column names.
        Based on 'opex_data_hybrid' schema loaded from configuration.
        """
        if not criteria:
            return {}

        # Retrieve the dynamic map from the global config
        # This pulls the map defined in config/schema.yaml
        schema_map = SCHEMA_CONFIG.get('schema_map', {})
        
        mapped_criteria = {}
        for key, value in criteria.items():
            # Normalize key
            norm_key = key.lower().strip()
            
            # Use mapped column if exists, else keep original
            db_column = schema_map.get(norm_key, norm_key)
            mapped_criteria[db_column] = value
            
        return mapped_criteria

    #####################################################
    ######### retrieve_relevant_docs ####################
    #####################################################
    def retrieve_relevant_docs(self, input_str: str, top_k: int = 20) -> List[Any]:
        """
        Main entry point for the agent to find data.
        """
        logger.info(f"[retrieve_relevant_docs] Input: {input_str}")

        # --- STEP 1: Extract structured intent ---
        try:
            intent_obj = self.extract_intent_from_prompt(input_str)
            logger.debug(f"[retrieve_relevant_docs] Extracted intent: {intent_obj}")
        except Exception as e:
            logger.error(f"[retrieve_relevant_docs] Intent extraction failed: {e}")
            intent_obj = {"intent": "retrieve", "criteria": {}}

        results = []

        # --- STEP 2: Handle Comparison (Multi-Entity) ---
        if intent_obj.get("intent") == "compare" and "entities" in intent_obj:
            logger.info(f"[retrieve_relevant_docs] Processing comparison for {len(intent_obj['entities'])} entities.")
            
            for entity_criteria in intent_obj["entities"]:
                # Map filters
                mapped_filters = self._map_criteria_to_schema(entity_criteria)
                
                # Create a specific query for this entity
                entity_query = f"{input_str} " + " ".join([f"{k}:{v}" for k, v in mapped_filters.items()])
                
                docs = self.retriever.search(
                    query_text=entity_query, 
                    filters=mapped_filters, 
                    limit=top_k
                )
                results.append({"criteria": mapped_filters, "docs": docs})
            
            return results

        # --- STEP 3: Handle Standard Retrieval ---
        else:
            raw_criteria = intent_obj.get("criteria", {})
            
            # Map filters to DB Schema
            mapped_filters = self._map_criteria_to_schema(raw_criteria)
            logger.info(f"Mapped DB Filters: {mapped_filters}")
            
            docs = self.retriever.search(
                query=input_str,
                filters=mapped_filters,
                limit=top_k
            )
            
            logger.info(f"[retrieve_relevant_docs] Found {len(docs)} documents.")
            return docs

    def generate_response(self, query: str, docs: List[Any]) -> str:
        """
        Parses retrieved documents and generates a user-friendly answer using the LLM.
        """
        if not docs:
            return "I couldn't find any relevant data to answer your question."

        # Format Context
        context_parts = []
        for i, doc in enumerate(docs):
            # Extract content robustly (handle objects or dicts)
            if hasattr(doc, 'page_content'):
                content = doc.page_content
            else:
                content = str(doc)
            
            # Try to clean up JSON strings if present
            try:
                if isinstance(content, str) and content.strip().startswith("{"):
                    content_dict = json.loads(content.replace("'", '"')) # Simple fallback
                    # Simplify context by removing vector arrays or internal IDs if possible
                    if 'vector' in content_dict: del content_dict['vector']
                    content = str(content_dict)
            except:
                pass

            context_parts.append(f"Record {i+1}: {content}")

        context_str = "\n".join(context_parts)

        # Generate Prompt
        system_prompt = (
            "You are a specialized Financial Assistant. Use the provided database records to answer the user's question.\n"
            "Guidelines:\n"
            "1. Answer strictly based on the provided Context.\n"
            "2. If the data contains lists of costs, summarize them (e.g., 'The total cost is...').\n"
            "3. If multiple records are found, present them clearly (e.g., bullet points).\n"
            "4. If the exact answer is not in the context, state 'I don't have enough information in the retrieved records.'\n\n"
            f"User Question: {query}\n\n"
            f"Context Records:\n{context_str}\n\n"
            "Answer:"
        )

        return self.llm_call(system_prompt)

    def extract_intent_from_prompt(self, user_input_prompt: str) -> Dict[str, Any]:
        """
        Uses LLM to parse user natural language into structured SQL-like filters.
        """
        valid_cols = ", ".join(self.schema_config.get("columns", {}).keys())
        
        system_prompt = (
            "You are a Query Parser for an Operational Expense (Opex) Database. "
            "Analyze the user's prompt and return a JSON object representing the search intent.\n\n"
            
            "**Supported Intents:**\n"
            "1. 'retrieve': Standard search. Return 'criteria' object with filters.\n"
            "2. 'compare': Comparing two specific items (e.g., two projects, two years). Return 'entities' list.\n\n"
            
            f"**Valid Filter Keys (Database Columns):**\n[{valid_cols}]\n"
            "If the user mentions a specific ID (e.g. 'Dept 50954'), extract it as 'department_id'.\n"
            "If the user mentions a year (e.g. 'FY25'), extract it as 'fiscal_year'.\n"
            "If the user asks for 'cost' or 'spend', map it to key 'cost' (which code will map to ods_mm).\n"
            "If the user asks for 'type of cost', map it to key 'type of cost' (which code will map to tm1_mm).\n\n"
            
            "**Examples:**\n"
            "User: 'Show me expenses for Dept 50954 in FY25.'\n"
            "JSON: {\"intent\": \"retrieve\", \"criteria\": {\"department_id\": 50954, \"fiscal_year\": 2025}}\n\n"
            
            "Return ONLY valid JSON."
            f"User Prompt: {user_input_prompt}"
        )

        llm_response = self.llm_call(system_prompt)
        
        try:
            cleaned_response = llm_response.replace("```json", "").replace("```", "").strip()
            intent_obj = json.loads(cleaned_response)
            if "criteria" not in intent_obj: intent_obj["criteria"] = {}
            return intent_obj
        except Exception as e:
            logger.error(f"Failed to parse LLM Intent: {e} | Raw: {llm_response}")
            return {"intent": "retrieve", "criteria": {}}

    def llm_call(self, prompt, max_retries=3):
        """
        Wrapper for QGenie Chat API with retry logic using the configured QGENIE_MODEL_NAME.
        """
        model = QGenieChat(
            model=self.model_name,
            api_key=Config.QGENIE_API_KEY,
            timeout=15000,
        )
        
        messages = [HumanMessage(content=prompt)]
        retries = 0
        
        while True:
            try:
                result = model.invoke(messages, max_tokens=2048, temperature=0.1)
                return result.content
            except QGenieAPIStatusException as e:
                logger.warning(f"LLM API Error: {e}")
                if retries < max_retries and e.http_status == 429:
                    time.sleep(2 ** retries)
                    retries += 1
                else:
                    return "{}"
            except Exception as e:
                logger.error(f"LLM Call Failed: {e}")
                return "{}"

    def format_llm_response(self, agent_response):
        """Standardizes response format from the Agent."""
        try:
            if hasattr(agent_response, "content"): return agent_response.content
            if isinstance(agent_response, str): return agent_response
            return str(agent_response)
        except Exception: return "Error formatting response."

    def get_tools_map(self, names: list[str]):
        """Returns the tool definitions for the LangChain Agent."""
        tool_mapping = {
            "retrieve_relevant_docs": self.retrieve_relevant_docs,
            "generate_response": self.generate_response,
            "llm_call": self.llm_call,
            "format_llm_response": self.format_llm_response,
        }
        tools_map = {}
        for name in names:
            if name in tool_mapping:
                tool = tool_mapping[name]
                tools_map[name] = {"call": tool, "schema": convert_to_openai_tool(tool)}
        return tools_map

if __name__ == "__main__":
    try:
        print("\n=== Initializing Agent Tools ===")
        tools = AgentUtils()
        print(f"✅ Tools initialized. Model: {tools.model_name}")
        
        # --- TEST 1: Intent Extraction ---
        print("\n=== Test 1: LLM Intent Extraction ===")
        test_query = "Find expenses for Dept 50954 in FY25"
        #test_query = "List all Dept and list project ids"
        print(f"Query: '{test_query}'")
        
        intent = tools.extract_intent_from_prompt(test_query)
        print("Extracted Intent (Raw):")
        pprint(intent)
        
        mapped = tools._map_criteria_to_schema(intent.get('criteria', {}))
        print("Mapped Filters:")
        pprint(mapped)
        
        # --- TEST 2: Full Retrieval Pipeline ---
        print("\n=== Test 2: Full Retrieval Pipeline ===")
        docs = tools.retrieve_relevant_docs(test_query, top_k=250)
        
        if docs:
            print(f"✅ Successfully retrieved {len(docs)} documents.")
            
            # --- TEST 3: Answer Synthesis ---
            print("\n=== Test 3: Answer Generation ===")
            answer = tools.generate_response(test_query, docs)
            print("Generated Answer:")
            pprint(answer)
            
        else:
            print("⚠️ No documents found. (Database might be empty or filters didn't match)")
            
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()