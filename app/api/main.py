from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Any
from app.graph.agent import graph
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Text2SQL Agent MVP", version="1.0.0")

class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    answer: str
    sql: Optional[str] = None
    context: Optional[str] = None
    result: Optional[List[Any]] = None  # <--- Added result field
    refused: bool = False

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    initial_state = {
        "question": req.question,
        "attempts": 0,
        "schema_context": "",
        "sql": "",
        "error": None,
        "result": [],
        "answer": "",
        "refused": False
    }
    final_state = graph.invoke(initial_state)
    
    return AskResponse(
        answer=final_state["answer"],
        sql=final_state.get("sql"),
        context=final_state.get("schema_context"),
        result=final_state.get("result"),
        refused=bool(final_state.get("refused", False))
    )

@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}