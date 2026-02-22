import pandas as pd
import json

def agent_visualization(retrieved_data, user_request, llm):
    # 1. Convert JSONL strings to DataFrame
    df = pd.DataFrame([json.loads(d) for d in retrieved_data])
    
    # 2. Ask LLM to analyze and generate plotting code
    prompt = f"""
    Data: {df.head().to_markdown()}
    User Request: {user_request}
    
    Task 1: Provide a text summary of insights.
    Task 2: Write Python code using Plotly Express to visualize this data if applicable.
    """
    
    response = llm.invoke(prompt)
    
    # 3. Execute the generated code (Sandbox execution) to get the figure object
    # exec(response.code) -> returns fig
    
    return {
        "analysis": response.text_analysis,
        "chart": response.generated_chart_object,
        "table": df # Return the raw table for display
    }