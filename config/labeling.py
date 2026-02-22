import yaml
import re
import os

class QuerySchemaMapper:
    def __init__(self, yaml_path="config/labels.yaml"):
        # Adjust path if not absolute or relative to current script
        if not os.path.exists(yaml_path):
            # Try looking in the same directory as the script if not found
            script_dir = os.path.dirname(os.path.abspath(__file__))
            potential_path = os.path.join(script_dir, yaml_path)
            if os.path.exists(potential_path):
                yaml_path = potential_path
            else:
                raise FileNotFoundError(f"{yaml_path} not found.")
            
        with open(yaml_path, 'r') as file:
            self.schema = yaml.safe_load(file)
            
        # Pre-process synonyms for faster lookup
        self.synonym_map = {}
        self._build_synonym_map()

    def _build_synonym_map(self):
        for table_name, table_data in self.schema.get('tables', {}).items():
            for col_name, col_data in table_data.get('columns', {}).items():
                # Map the column name itself
                self._add_to_map(col_name, table_name, col_name, col_data)
                # Map synonyms
                for synonym in col_data.get('synonyms', []):
                    self._add_to_map(synonym, table_name, col_name, col_data)

    def _add_to_map(self, keyword, table, column, col_data):
        keyword_clean = keyword.lower().strip()
        if keyword_clean not in self.synonym_map:
            self.synonym_map[keyword_clean] = []
        # Avoid duplicate entries for the same column under the same keyword
        existing_entry = next((item for item in self.synonym_map[keyword_clean] 
                             if item['table'] == table and item['column'] == column), None)
        if not existing_entry:
            self.synonym_map[keyword_clean].append({
                'table': table,
                'column': column,
                'description': col_data.get('description')
            })

    def get_relevant_schema_context(self, user_query):
        """
        Analyzes the user query and returns a text description of relevant columns.
        """
        query_lower = user_query.lower()
        found_matches = {}

        # Sort synonyms by length (descending) to prioritize longer phrases
        # e.g., match "department lead" before "lead"
        sorted_keywords = sorted(self.synonym_map.keys(), key=len, reverse=True)

        # Track covered parts of the string to avoid double matching if desired (optional)
        # For now, we allow overlapping matches but we might want to mask found terms.
        
        for keyword in sorted_keywords:
            # Use regex word boundary to avoid partial matches
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, query_lower):
                matches = self.synonym_map[keyword]
                for match in matches:
                    key = f"{match['table']}.{match['column']}"
                    if key not in found_matches:
                        found_matches[key] = match

        if not found_matches:
            return "No specific schema mappings found for this query."

        # Format output
        output_lines = ["Relevant Schema Information:"]
        for key, info in found_matches.items():
            output_lines.append(f"- Table: {info['table']}, Column: {info['column']}")
            output_lines.append(f"  Description: {info['description']}")
        
        return "\n".join(output_lines)

if __name__ == "__main__":
    # Example usage
    mapper = QuerySchemaMapper()
    query = "Who is the manager for the WIN Maintenance project?"
    print(f"Query: {query}")
    print(mapper.get_relevant_schema_context(query))
