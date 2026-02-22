def agent_data_connector(intent: UserIntent, vector_store):
    results = []
    
    if intent.query_type == "semantic":
        # Pure vector search
        results = vector_store.similarity_search(intent.search_query, k=5)
        
    elif intent.query_type == "sql":
        # Metadata filtering (simulating SQL on Vector DB)
        # Assuming metadata in vector DB maps to Excel columns
        results = vector_store.similarity_search(
            intent.search_query, 
            filter=convert_sql_to_metadata_filter(intent.sql_logic) 
        )
        
    elif intent.query_type == "hybrid":
        # Combination of BM25 (keyword) and Vector search
        results = vector_store.max_marginal_relevance_search(intent.search_query, k=5)
        
    return [doc.page_content for doc in results] # Returns list of JSON strings