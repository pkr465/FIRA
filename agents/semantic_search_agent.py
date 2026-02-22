import logging
import json
from typing import List, Dict, Any

from config.config import Config
from agents.utils.agent_utils import AgentUtils

# --- Added Import Logic ---
try:
    from config.labeling import QuerySchemaMapper
except ImportError:
    # Fallback if running locally/testing without full package structure
    try:
        from config.labeling import QuerySchemaMapper
    except ImportError:
        QuerySchemaMapper = None

# Configure Logging
logger = logging.getLogger(__name__)

class SemanticSearchAgent:
    """
    Agent responsible for Retrieval Augmented Generation (RAG) over unstructured text.
    It answers 'How-to', 'What is', and 'Summarize' style questions.
    """

    def __init__(self):
        self.utils = AgentUtils()
        self.retriever = self.utils.retriever  # Direct access to the VectorRetriever
        
        # --- Added Schema Mapper Initialization ---
        self.schema_mapper = None
        if QuerySchemaMapper:
            try:
                self.schema_mapper = QuerySchemaMapper()
            except Exception as e:
                logger.warning(f"Failed to initialize QuerySchemaMapper: {e}")
        
        # Configuration
        self.top_k = 5  # Number of chunks to retrieve
        self.similarity_threshold = 0.75 # Minimum relevance score (if supported by retriever)

    def run(self, user_query: str) -> str:
        """
        Main execution flow:
        1. Expand Query (Generate synonyms/related terms)
        2. Retrieve Documents (Vector Search)
        3. Synthesize Answer (LLM)
        """
        logger.info(f"--- Semantic Search Started: '{user_query}' ---")

        # 1. OPTIONAL: Expand the query for better recall
        # e.g., "Opex variance" -> "Operational expense variance analysis report"
        expanded_queries = self._expand_query(user_query)
        logger.info(f"Expanded Queries: {expanded_queries}")

        # 2. Retrieve Documents
        # We search using the original query AND the best expanded variation
        raw_docs = self._retrieve_documents(user_query, expanded_queries)
        
        if not raw_docs:
            return "I searched the knowledge base but couldn't find any relevant documents matches your query."

        # 3. Synthesize Answer
        response = self._synthesize_answer(user_query, raw_docs)
        
        return response

    def _expand_query(self, original_query: str) -> List[str]:
        """
        Uses LLM to generate 1-2 search-optimized variations of the user's query.
        This helps when the user uses slang or vague terms.
        """
        # --- Added Schema Context Retrieval ---
        schema_context = ""
        if self.schema_mapper:
            try:
                schema_context = self.schema_mapper.get_relevant_schema_context(original_query)
            except Exception as e:
                logger.warning(f"Error getting schema context: {e}")

        # --- Updated Prompt ---
        prompt = (
            f"You are a search query optimizer. The user is asking: '{original_query}'.\n\n"
            f"{schema_context}\n\n"
            "Generate 2 alternative search queries that are more formal or specific to "
            "financial/operational documentation. "
            "If the schema context provides specific terminology (e.g., 'dept_lead' for 'manager'), "
            "use those official terms in the variations.\n"
            "Return ONLY a JSON list of strings. Example: [\"query1\", \"query2\"]"
        )
        
        try:
            response = self.utils.llm_call(prompt)
            # Clean generic markdown
            cleaned = response.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned)
        except Exception:
            # Fallback to just the original if expansion fails
            return [original_query]

    def _retrieve_documents(self, original_query: str, variations: List[str]) -> List[Any]:
        """
        Searches the vector store.
        (Logic assumes utils.retriever.search takes a text query string)
        """
        all_docs = []
        seen_content = set()

        # Search with original query first (highest priority)
        queries_to_run = [original_query] + variations[:1] # Take top 1 variation
        
        for q in queries_to_run:
            try:
                # Assuming utils.retriever.search returns a list of LangChain Document objects 
                # or objects with .page_content and .metadata
                docs = self.retriever.search(query=q, limit=self.top_k)
                
                for doc in docs:
                    # Extract text content
                    content = getattr(doc, 'page_content', str(doc))
                    
                    # Deduplicate results
                    if content not in seen_content:
                        seen_content.add(content)
                        all_docs.append(doc)
                        
            except Exception as e:
                logger.error(f"Vector search failed for query '{q}': {e}")

        return all_docs[:self.top_k] # Return top unique results

    def _synthesize_answer(self, query: str, docs: List[Any]) -> str:
        """
        Feeds the retrieved chunks into the LLM to generate a coherent answer.
        """
        # 1. Prepare Context String
        context_parts = []
        sources = []
        
        for i, doc in enumerate(docs):
            content = getattr(doc, 'page_content', str(doc))
            metadata = getattr(doc, 'metadata', {})
            
            # Format source name
            source_name = metadata.get('source', 'Unknown Document')
            page_num = metadata.get('page', '')
            source_ref = f"{source_name} (Pg {page_num})" if page_num else source_name
            sources.append(source_ref)

            context_parts.append(f"--- DOCUMENT FRAGMENT {i+1} (Source: {source_ref}) ---\n{content}\n")

        context_str = "\n".join(context_parts)
        unique_sources = list(set(sources))

        # 2. Construct Prompt
        system_prompt = (
            "You are a Senior Financial & Resource Planning Analyst at a Fortune 500 company.\n"
            "Use the provided Document Fragments to answer the User's Question.\n\n"

            "**Communication guidelines:**\n"
            "1. Answer ONLY based on the context provided. Do not hallucinate external facts.\n"
            "2. If the context does not contain the answer, say "
            "'I was unable to locate that information in the available documents.'\n"
            "3. Maintain a professional, executive-level tone throughout your response.\n"
            "4. Use precise financial and resource planning terminology.\n"
            "5. Structure longer answers with clear paragraphs. Use numbered steps for procedures.\n"
            "6. Highlight key figures, thresholds, or policy requirements when present.\n"
            "7. Where relevant, note any caveats, effective dates, or conditions that apply.\n\n"

            f"**Context:**\n{context_str}\n\n"
            f"**User Question:** {query}\n\n"
            "**Professional Response:**"
        )

        # 3. Call LLM
        answer = self.utils.llm_call(system_prompt)

        # 4. Append Sources (if not already mentioned by LLM, though we force it usually)
        # We manually append a citations block to ensure visibility
        final_output = f"{answer}\n\n**References:**\n" + "\n".join([f"- {s}" for s in unique_sources])
        
        return final_output

if __name__ == "__main__":
    # --- TEST HARNESS ---
    print("\n=== Initializing Semantic Search Agent ===")
    try:
        agent = SemanticSearchAgent()
        
        # Test Cases
        test_queries = [
            "What is the policy for business travel meals?",
            "How do I create a new project code in ODS?",
            "Summarize the Q3 Opex Variance report."
        ]

        print(f"\nRunning {len(test_queries)} test cases...\n")

        for q in test_queries:
            print(f"❓ User: {q}")
            response = agent.run(q)
            print(f"🤖 Agent:\n{response}\n")
            print("-" * 60)

    except Exception as e:
        logger.error(f"Initialization Failed: {e}")
        import traceback
        traceback.print_exc()