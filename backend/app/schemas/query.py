from pydantic import BaseModel
from uuid import UUID
from typing import List, Dict, Any, Optional

class QueryRequest(BaseModel):
    db_id: UUID
    question: str

class QueryResponse(BaseModel):
    sql: str
    explanation: str
    confidence: float
    results: Optional[List[Dict[str, Any]]] = None
    execution_time: Optional[float] = None  # in seconds
    cached: bool = False
