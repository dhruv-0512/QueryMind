from pydantic import BaseModel, model_validator
from uuid import UUID
from typing import List, Dict, Any, Optional


class QueryRequest(BaseModel):
    db_id: Optional[UUID] = None          # backward-compat: single datasource
    db_ids: Optional[List[UUID]] = None   # new: multiple datasources
    question: str

    @model_validator(mode="after")
    def check_at_least_one_db(self) -> "QueryRequest":
        if self.db_id is None and not self.db_ids:
            raise ValueError("Either db_id or db_ids must be provided.")
        return self

    @property
    def resolved_db_ids(self) -> List[UUID]:
        """Always returns a list of db IDs to query."""
        if self.db_ids:
            return self.db_ids
        if self.db_id:
            return [self.db_id]
        return []


class QueryResponse(BaseModel):
    sql: str
    explanation: str
    confidence: float
    results: Optional[List[Dict[str, Any]]] = None
    execution_time: Optional[float] = None
    cached: bool = False
    datasources_used: Optional[List[str]] = None  # list of db_ids used
