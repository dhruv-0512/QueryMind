import json
import logging
import asyncio
import time
from typing import Dict, Any, List, Tuple
import google.generativeai as genai
from app.config import settings
from app.utils.embeddings import is_api_key_configured
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

class SqlService:
    def __init__(self) -> None:
        if is_api_key_configured():
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.model = genai.GenerativeModel("gemini-1.5-pro")
            logger.info("Gemini Model gemini-1.5-pro initialized for SQL Service.")
        else:
            logger.warning("GEMINI_API_KEY is not configured. SQL service will use mock generation.")
            self.model = None

    def _extract_table_from_schema(self, schema_context: str) -> str:
        """Extract the table name from a CREATE TABLE DDL snippet."""
        import re
        match = re.search(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["\w]+\."?(\w+)"?', schema_context, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"?(\w+)"?', schema_context, re.IGNORECASE)
        return match.group(1) if match else "my_table"

    def _extract_columns_from_schema(self, schema_context: str) -> List[str]:
        """Extract column names from a CREATE TABLE DDL snippet."""
        import re
        cols = []
        for line in schema_context.split("\n"):
            line = line.strip()
            m = re.match(r'^"?(\w+)"?\s+(TEXT|INTEGER|BIGINT|BOOLEAN|TIMESTAMP|FLOAT|DOUBLE|NUMERIC|SERIAL|UUID|DATE|VARCHAR)', line, re.IGNORECASE)
            if m and not line.startswith("CREATE") and not line.startswith("PRIMARY") and not line.startswith("FOREIGN") and not line.startswith("INDEX") and not line.startswith(")"):
                cols.append(m.group(1))
        return cols

    def _match_column(self, keyword: str, available_cols: List[str]) -> str:
        """Find the best matching column for a keyword."""
        kw_lower = keyword.lower()
        for col in available_cols:
            if kw_lower in col.lower():
                return col
        return keyword

    async def generate_sql(self, schema_context: str, user_question: str) -> Dict[str, Any]:
        if not is_api_key_configured():
            logger.info("Mock SQL fallback generated (No Gemini key).")
            tbl = self._extract_table_from_schema(schema_context)
            cols = self._extract_columns_from_schema(schema_context)
            question_lower = user_question.lower()
            sql = f"SELECT * FROM {tbl} LIMIT 5;"
            if "new york" in question_lower:
                pk = self._match_column("city", cols)
                sql = f"SELECT * FROM {tbl} WHERE {pk} = 'New York';"
            elif "starting with" in question_lower or "starts with" in question_lower:
                import re
                m = re.search(r"starting with ['\"]?(\w)['\"]?", question_lower)
                if not m:
                    m = re.search(r"starts with ['\"]?(\w)['\"]?", question_lower)
                prefix = m.group(1).upper() if m else ""
                target_col = cols[0] if cols else "*"
                if "name" in question_lower or "first" in question_lower:
                    target_col = self._match_column("name", cols)
                sql = f"SELECT * FROM {tbl} WHERE {target_col} LIKE '{prefix}%';"
            elif "name" in question_lower or "city" in question_lower:
                selected = []
                if "name" in question_lower:
                    selected.append(self._match_column("name", cols))
                if "city" in question_lower:
                    selected.append(self._match_column("city", cols))
                if not selected:
                    selected = ["*"]
                selected_str = ", ".join(selected)
                sql = f"SELECT {selected_str} FROM {tbl};"
            return {
                "sql": sql,
                "explanation": "Mock SQL generated for local testing.",
                "confidence": 0.95
            }

        if not self.model:
            raise RuntimeError("Gemini API client is not configured.")

        prompt = f"""You are a SQL expert. Given the following database schema:
{schema_context}

Generate a valid PostgreSQL SELECT query for this question:
{user_question}

Rules:
- Only generate SELECT statements
- Use exact table and column names from schema
- Return JSON: {{"sql": "...", "explanation": "...", "confidence": 0.0-1.0}}
"""

        try:
            response = await self.model.generate_content_async(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            raw_text = response.text.strip()
            result = json.loads(raw_text)
            if not isinstance(result, dict) or "sql" not in result or "explanation" not in result or "confidence" not in result:
                raise ValueError("Response missing required keys (sql, explanation, confidence).")
            return result
        except json.JSONDecodeError as je:
            logger.error(f"Failed to parse Gemini JSON: {je}")
            raise ValueError("Gemini returned invalid JSON. Please retry.")
        except Exception as e:
            logger.error(f"Gemini SQL generation error: {e}")
            raise e

    async def execute_pg_query(
        self,
        session: AsyncSession,
        schema_name: str,
        sql: str,
        max_rows: int = 1000,
        timeout: float = 30.0,
    ) -> Tuple[List[Dict[str, Any]], float]:
        start = time.time()
        safe_schema = schema_name

        await session.execute(text(f"SET LOCAL search_path TO {safe_schema}, public"))

        try:
            result = await asyncio.wait_for(
                session.execute(text(sql)),
                timeout=timeout,
            )
            rows = result.fetchmany(max_rows)
            columns = list(result.keys())
            data = [dict(zip(columns, row)) for row in rows]
            latency = time.time() - start

            for row_dict in data:
                for key, val in row_dict.items():
                    if hasattr(val, "isoformat"):
                        row_dict[key] = val.isoformat()
                    elif isinstance(val, (bytes, memoryview)):
                        row_dict[key] = str(val)

            return data, latency
        except asyncio.TimeoutError:
            await session.rollback()
            raise TimeoutError(f"Query execution timed out after {timeout}s.")
        except Exception as e:
            await session.rollback()
            logger.error(f"PostgreSQL query execution error: {e}")
            raise e

sql_service = SqlService()
