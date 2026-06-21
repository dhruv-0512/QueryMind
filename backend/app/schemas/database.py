from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import List, Optional

class DatabaseResponse(BaseModel):
    id: UUID
    name: str
    schema_name: str
    table_name: str
    row_count: int
    file_format: str
    created_at: datetime

    class Config:
        from_attributes = True

class DatabaseUploadResponse(BaseModel):
    id: UUID
    name: str
    message: str
    tables: List[str]
