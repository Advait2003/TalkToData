import sqlglot
from sqlglot import exp

def validate_and_sanitize_sql(sql_query: str) -> str:
    """
    Validates that the query is a single, read-only SELECT statement.
    Injects a LIMIT clause if one is missing.
    """
    try:
        statements = sqlglot.parse(sql_query, read="postgres")
    except Exception as e:
        raise ValueError(f"Invalid SQL syntax: {e}")
    
    if len(statements) > 1:
        raise ValueError("Multiple statements are not allowed.")
    
    stmt = statements[0]
    
    # Restrict to SELECT statements only
    if not isinstance(stmt, exp.Select):
        raise ValueError("Only SELECT statements are permitted.")
    
    # Ensure a LIMIT clause exists to prevent runaway queries
    if not stmt.find(exp.Limit):
        stmt = stmt.limit(100)
        
    return stmt.sql(dialect="postgres")
