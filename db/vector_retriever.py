import logging
from sqlalchemy import create_engine, text
from typing import List, Dict, Optional, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VectorRetriever:
    def __init__(self, 
                 connection_string: str, 
                 embedding_client: Any, 
                 schema_config: Dict[str, Any]):
        """
        A Project-Agnostic Hybrid Retriever.
        
        :param connection_string: Full DB connection string.
        :param embedding_client: Object with .embed_query(text) method.
        :param schema_config: Dict with 'table_name', 'columns', and optional 'vector_column'.
        """
        self.engine = create_engine(connection_string)
        self.embedder = embedding_client
        self.schema_config = schema_config
        
        # Load Configuration
        self.table_name = self.schema_config.get("table_name", "generic_hybrid_data")
        
        # dynamic vector column name (Defaults to 'vector' if not in config)
        self.vector_col = self.schema_config.get("vector_column", "vector")
        
        # Defines which fields are real SQL columns. 
        self.known_columns = set(self.schema_config.get("columns", {}).keys())
        self.known_columns.add("uuid")
        self.known_columns.add(self.vector_col)

    def _get_embedding_vector(self, text: str) -> List[float]:
        """Helper to handle different embedding client interfaces."""
        if hasattr(self.embedder, "embed_query"):
            return self.embedder.embed_query(text)
        elif hasattr(self.embedder, "get_embedding"):
            return self.embedder.get_embedding(text)
        else:
            raise AttributeError("Embedding client must have 'embed_query' or 'get_embedding' method.")

    def _build_filter_clauses(self, filters: Dict[str, Any], params: Dict[str, Any]) -> List[str]:
        clauses = []
        for key, value in filters.items():
            param_key = f"filter_{key}"
            
            # Skip if the filter is trying to query the vector column directly
            if key == self.vector_col:
                continue

            if key in self.known_columns:
                # 1. Standard SQL Column Filter
                clauses.append(f"{key} = :{param_key}")
                params[param_key] = value
            else:
                # 2. JSONB Filter (Dynamic)
                clauses.append(f"additional_data->>'{key}' = :{param_key}")
                params[param_key] = str(value)
                
        return clauses

    def search(self, 
               query: Optional[str] = None, 
               filters: Optional[Dict[str, Any]] = None, 
               limit: int = 5) -> List[Dict]:
        
        filters = filters or {}
        params = {"limit": limit}
        where_clauses = self._build_filter_clauses(filters, params)
        
        # Construct Query
        sql_query = f"SELECT *, "
        
        if query:
            # Generate vector
            query_vector = self._get_embedding_vector(query)
            params["embedding_param"] = str(query_vector)
            
            # Cosine Similarity: 1 - ({vector_col} <=> :embedding_param)
            # We use the dynamic column name here
            sql_query += f" 1 - ({self.vector_col} <=> :embedding_param) as similarity "
        else:
            sql_query += " 0 as similarity "

        sql_query += f"FROM {self.table_name} "

        if where_clauses:
            sql_query += "WHERE " + " AND ".join(where_clauses) + " "

        # Ordering Logic
        if query:
            sql_query += f"ORDER BY {self.vector_col} <=> :embedding_param ASC "
        else:
            sql_query += "ORDER BY uuid DESC "

        sql_query += "LIMIT :limit"

        results = []
        try:
            with self.engine.connect() as conn:
                result_proxy = conn.execute(text(sql_query), params)
                
                for row in result_proxy:
                    row_dict = row._mapping
                    
                    # Filter out heavy/internal columns from metadata
                    exclude_cols = ['similarity', self.vector_col]
                    
                    results.append({
                        "uuid": str(row_dict.get("uuid")),
                        "score": round(row_dict.get("similarity", 0), 4),
                        "metadata": {
                            k: v for k, v in row_dict.items() 
                            if k not in exclude_cols
                        }
                    })
                    
        except Exception as e:
            logger.error(f"Search query failed: {e}")
            raise

        return results