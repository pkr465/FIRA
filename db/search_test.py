from db.vector_retriever import VectorRetriever
import json

def print_results(results, title):
    print(f"\n--- {title} ---")
    if not results:
        print("No results found.")
        return
        
    for r in results:
        print(f"[Score: {r['score']}] {r['metadata']['business_unit']} - {r['content'][:100]}...")

def main():
    # Initialize the API
    retriever = VectorRetriever()

    # 1. Pure Relational Search (Filter by Year and Dept)
    print("running relational search...")
    relational_results = retriever.search(
        filters={"year": 2024, "business_unit": "Engineering"}
    )
    print_results(relational_results, "Relational Results (2024 Engineering)")

    # 2. Semantic Search (No filters, just meaning)
    print("running semantic search...")
    semantic_results = retriever.search(
        query_text="High costs associated with software licenses",
        limit=3
    )
    print_results(semantic_results, "Semantic Results ('Software Licenses')")

    # 3. Hybrid Search (Semantic query constrained by filters)
    print("running hybrid search...")
    hybrid_results = retriever.search(
        query_text="Travel expenses",
        filters={"year": 2025}, # Only look in 2025
        limit=3
    )
    print_results(hybrid_results, "Hybrid Results ('Travel' in 2025)")

if __name__ == "__main__":
    main()