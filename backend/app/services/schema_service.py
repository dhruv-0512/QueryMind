import logging
from typing import Dict, Any, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

class SchemaService:
    @staticmethod
    def generate_ddl_chunks(schema_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert schema metadata into text chunks (one DDL chunk per table)."""
        chunks = []
        for table, meta in schema_metadata.items():
            ddl_chunk = meta.get("ddl", "")
            if meta.get("index_ddls"):
                ddl_chunk += "\n" + "\n".join(meta["index_ddls"])

            ddl_chunk = ddl_chunk.strip()
            if ddl_chunk and not ddl_chunk.endswith(";"):
                ddl_chunk += ";"

            chunks.append({
                "table_name": table,
                "chunk_text": ddl_chunk,
                "columns": [col["name"] for col in meta.get("columns", [])]
            })
        return chunks

schema_service = SchemaService()
