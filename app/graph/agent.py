from typing import TypedDict, List, Optional, Any
import os
import psycopg2
from langgraph.graph import StateGraph, END
from app.guardrails import validate_and_sanitize_sql
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma

import sqlglot
from sqlglot import exp



class State(TypedDict):
    question: str
    schema_context: str
    sql: str
    error: Optional[str]
    result: List[Any]
    attempts: int
    answer: str
    refused: bool

def get_db_connection():
    # Make sure port is 5433 to match docker-compose.yml
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:password@127.0.0.1:5433/chinook")
    return psycopg2.connect(db_url)

def retrieve_schema(state: State) -> State:
    try:
        embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
        vectorstore = Chroma(persist_directory="./chroma_db", embedding_function=embeddings)
        docs = vectorstore.similarity_search(state["question"], k=2)
        schema_lines = [doc.page_content for doc in docs]
        state["schema_context"] = "\n".join(schema_lines)
    except Exception as e:
        state["schema_context"] = "Tables: customer, invoice, track, employee"
    return state

def guardrail_check(state: State) -> State:
    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite")
    
    prompt = f"""
    You are a security and relevance guardrail for a Text2SQL database assistant.
    The database contains ONLY the following tables and business domain (Chinook Music Store):
    - customer (buyer account details)
    - invoice (purchases made by customers)
    - track (songs and audio tracks, pricing, composer)
    - employee (staff hierarchy and support reps)

    User Question: "{state['question']}"

    Is this question answerable using data from a music store database (customers, invoices, tracks, employees)? 
    Answer ONLY with "YES" or "NO". Do not include any other text or punctuation.
    """
    
    response = llm.invoke(prompt)
    content = response.content
    if isinstance(content, list):
        content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content])
    
    decision = str(content).strip().upper()
    
    if "NO" in decision:
        state["refused"] = True
        state["answer"] = "I'm sorry, but I can only answer questions related to the music store database (customers, invoices, tracks, and employees)."
        state["sql"] = ""
        state["result"] = []
    else:
        state["refused"] = False
        
    return state

def generate_sql(state: State) -> State:
    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite")
    
    prompt = f"""
    You are an expert PostgreSQL SQL generator. 
    Given the database schema context below, write a valid PostgreSQL query answering the user question.
    Return ONLY the raw SQL query, no markdown syntax blocks, no explanations.
    
    Schema Context:
    {state['schema_context']}
    
    User Question: {state['question']}
    """
    
    response = llm.invoke(prompt)
    
    # Safely handle if response.content is a list or a string
    content = response.content
    if isinstance(content, list):
        # Extract text blocks if it's a structured list
        content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content])
    
    state["sql"] = str(content).strip().replace("```sql", "").replace("```", "").strip()
    state["attempts"] += 1
    return state

def validate_sql(state: State) -> State:
    try:
        # Parse the query specifically for PostgreSQL dialect
        parsed_queries = sqlglot.parse(state["sql"], read="postgres")
        
        if not parsed_queries:
            state["error"] = "Empty SQL query generated."
            return state
            
        # Ensure every statement is strictly a SELECT statement
        for query in parsed_queries:
            if not isinstance(query, exp.Select):
                state["error"] = "Security Policy Violation: Only read-only SELECT queries are allowed."
                return state
                
        state["error"] = None
    except Exception as e:
        state["error"] = f"Invalid SQL syntax: {str(e)}"
        
    return state

def execute_sql(state: State) -> State:
    """Executes the validated SQL query against PostgreSQL."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Set a statement timeout to prevent runaway queries (e.g., 3 seconds)
        cursor.execute("SET statement_timeout = 3000;")
        
        cursor.execute(state["sql"])
        
        # Fetch column names and rows
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        
        # Convert rows into a list of dictionaries for clean state handling
        state["result"] = [dict(zip(columns, row)) for row in rows]
        state["error"] = None
        
        cursor.close()
    except Exception as e:
        state["error"] = str(e)
        state["result"] = None
    finally:
        if conn:
            conn.close()
    return state

def correct_sql(state: State) -> State:
    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite")
    
    prompt = f"""
    You previously generated this invalid SQL: {state['sql']}
    It resulted in this database error: {state['error']}
    
    Fix the SQL query based on the schema context below. Return ONLY the raw SQL, no markdown code blocks, no explanations.
    
    Schema Context: {state['schema_context']}
    Question: {state['question']}
    """
    
    response = llm.invoke(prompt)
    
    # Safely handle if response.content comes back as a list or a string
    content = response.content
    if isinstance(content, list):
        content = "".join([item.get("text", "") if isinstance(item, dict) else str(item) for item in content])
        
    state["sql"] = str(content).strip().replace("```sql", "").replace("```", "").strip()
    state["attempts"] += 1
    return state

def respond(state: State) -> State:
    if state.get("error"):
        state["answer"] = f"Failed to execute query: {state['error']}"
        state["result"] = []
    else:
        rows = state.get("result", [])
        state["answer"] = f"Successfully executed query. Retrieved {len(rows)} rows."
    return state

def check_validation_error(state: State):
    return "correct_sql" if state.get("error") else "execute_sql"

def check_execution_error(state: State):
    if state.get("error"):
        return "correct_sql" if state["attempts"] < 3 else "respond"
    return "respond"


workflow = StateGraph(State)

# 1. Add all your nodes
workflow.add_node("guardrail", guardrail_check)
workflow.add_node("retrieve_schema", retrieve_schema)
workflow.add_node("generate_sql", generate_sql)
workflow.add_node("validate_sql", validate_sql)  # <-- Make sure validate_sql node is added
workflow.add_node("execute_sql", execute_sql)
workflow.add_node("correct_sql", correct_sql)
workflow.add_node("respond", respond)

# 2. Define edges and routing
workflow.set_entry_point("guardrail")

def check_refusal(state: State):
    return "refused" if state.get("refused", False) else "pass"

workflow.add_conditional_edges(
    "guardrail",
    check_refusal,
    {"refused": END, "pass": "retrieve_schema"}
)

workflow.add_edge("retrieve_schema", "generate_sql")

# --- PASTE THE NEW WORKFLOW EDGES HERE ---
workflow.add_edge("generate_sql", "validate_sql")
workflow.add_edge("correct_sql", "validate_sql")

def should_execute_or_correct(state: State):
    if state.get("error"):
        if state["attempts"] < 3:
            return "correct"
        else:
            return "fail"
    return "execute"

workflow.add_conditional_edges(
    "validate_sql",
    should_execute_or_correct,
    {
        "correct": "correct_sql",
        "fail": "respond",
        "execute": "execute_sql"
    }
)

workflow.add_edge("execute_sql", "respond")
workflow.add_edge("respond", END)

# Compile the graph
graph = workflow.compile()