import json
import logging
import asyncio
import re
import time
import uuid
from decimal import Decimal
from typing import Dict, Any, List, Tuple, Optional
import google.generativeai as genai
from app.config import settings
from app.utils.embeddings import is_api_key_configured
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

RAG_DIRECT_THRESHOLD = 0.78
SQL_KEYWORDS = {
    "select", "from", "where", "group", "by", "order", "having", "join",
    "inner", "left", "right", "outer", "on", "as", "and", "or", "not",
    "in", "like", "between", "is", "null", "distinct", "limit", "offset",
    "asc", "desc", "count", "sum", "avg", "max", "min", "case", "when",
    "then", "else", "end", "with", "union", "all", "exists",
}


class SqlService:
    def __init__(self) -> None:
        if is_api_key_configured():
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.model = genai.GenerativeModel("gemini-2.5-flash")
            logger.info("Gemini Model gemini-2.5-flash initialized for SQL Service.")
        else:
            logger.warning("GEMINI_API_KEY is not configured. SQL service will use mock generation.")
            self.model = None

    def _extract_table_from_schema(self, schema_context: str) -> str:
        match = re.search(
            r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["\w]+\."?(\w+)"?',
            schema_context,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)
        match = re.search(
            r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"?(\w+)"?',
            schema_context,
            re.IGNORECASE,
        )
        return match.group(1) if match else "my_table"

    def _extract_columns_from_schema(self, schema_context: str) -> List[str]:
        cols = []
        for line in schema_context.split("\n"):
            line = line.strip()
            m = re.match(
                r'^"?(\w+)"?\s+(TEXT|INTEGER|BIGINT|BOOLEAN|TIMESTAMP|FLOAT|DOUBLE|NUMERIC|SERIAL|UUID|DATE|VARCHAR)',
                line,
                re.IGNORECASE,
            )
            if m and not line.startswith(("CREATE", "PRIMARY", "FOREIGN", "INDEX", ")")):
                cols.append(m.group(1))
        return cols

    def _match_column(self, keyword: str, available_cols: List[str]) -> str:
        kw_lower = keyword.lower()
        for col in available_cols:
            if kw_lower in col.lower() or col.lower() in kw_lower:
                return col
        return keyword

    def _adapt_sql_from_example(
        self,
        example_sql: str,
        schema_context: str,
    ) -> Optional[str]:
        """Map retrieved SQL structure onto the user's schema (RAG-first path)."""
        target_table = self._extract_table_from_schema(schema_context)
        schema_cols = self._extract_columns_from_schema(schema_context)
        if not target_table:
            return None

        adapted = example_sql.strip().rstrip(";")

        from_match = re.search(r"\bFROM\s+[`\"]?\w+[`\"]?", adapted, re.IGNORECASE)
        if from_match:
            adapted = re.sub(
                r"\bFROM\s+[`\"]?\w+[`\"]?",
                f"FROM {target_table}",
                adapted,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            return None

        adapted = re.sub(
            r"\bJOIN\s+[`\"]?\w+[`\"]?",
            f"JOIN {target_table}",
            adapted,
            flags=re.IGNORECASE,
        )

        tokens = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", adapted))
        col_map = {}
        for token in tokens:
            low = token.lower()
            if low in SQL_KEYWORDS or token.isdigit():
                continue
            if token == target_table:
                continue
            mapped = self._match_column(token, schema_cols)
            if mapped != token:
                col_map[token] = mapped

        for old, new in sorted(col_map.items(), key=lambda x: -len(x[0])):
            adapted = re.sub(rf"\b{re.escape(old)}\b", new, adapted)

        if not adapted.upper().startswith("SELECT"):
            return None
        return adapted + ";"

    def _try_rag_direct(
        self,
        schema_context: str,
        user_question: str,
        retrieved_examples: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not retrieved_examples:
            return None

        top = retrieved_examples[0]
        similarity = top.get("similarity", 0.0)
        if similarity < RAG_DIRECT_THRESHOLD:
            return None

        adapted_sql = self._adapt_sql_from_example(top["sql"], schema_context)
        if not adapted_sql:
            return None

        logger.info(
            f"RAG-direct adaptation (similarity={similarity:.2f}): "
            f"'{top['question'][:60]}...'"
        )
        return {
            "sql": adapted_sql,
            "explanation": (
                f"Adapted from similar example (similarity {similarity:.0%}): "
                f"'{top['question']}'"
            ),
            "confidence": min(0.98, similarity),
            "rag_mode": "direct",
        }

    def _build_rag_prompt(
        self,
        schema_context: str,
        user_question: str,
        retrieved_examples: List[Dict[str, Any]],
    ) -> str:
        examples_block = ""
        if retrieved_examples:
            parts = []
            for i, ex in enumerate(retrieved_examples, 1):
                sim = ex.get("similarity")
                sim_note = f" (similarity: {sim:.0%})" if sim is not None else ""
                parts.append(
                    f"Example {i}{sim_note}:\n"
                    f"Question:\n{ex['question']}\n"
                    f"SQL:\n{ex['sql']}"
                )
            examples_block = "SIMILAR SQL EXAMPLES:\n" + "\n\n".join(parts)

        top_hint = ""
        if retrieved_examples:
            top = retrieved_examples[0]
            top_hint = (
                f"\nPRIMARY PATTERN (highest similarity): "
                f"Follow the SQL structure of Example 1 closely. "
                f"Only remap table and column names to match SCHEMA.\n"
            )

        return f"""SCHEMA:
{schema_context}

{examples_block}

USER QUESTION:
{user_question}

Instructions:
You are a SQL adaptation engine, not a free-form generator.
{top_hint}
1. Start from the most similar example's SQL structure.
2. Remap ALL table and column names to match SCHEMA exactly.
3. Preserve clauses (WHERE, GROUP BY, JOIN, ORDER BY, aggregates) from the example.
4. Do NOT invent new tables or columns not in SCHEMA.
5. Retrieved SQL is a structural template only — adapt it, do not copy identifiers.
6. Generate PostgreSQL SELECT only.

Return JSON: {{"sql": "...", "explanation": "...", "confidence": 0.0-1.0}}
"""

    async def generate_sql(
        self,
        schema_context: str,
        user_question: str,
        retrieved_examples: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        retrieved_examples = retrieved_examples or []

        rag_result = self._try_rag_direct(schema_context, user_question, retrieved_examples)
        if rag_result:
            return rag_result

        if not is_api_key_configured():
            logger.info("Mock SQL fallback (no Gemini key).")
            tbl = self._extract_table_from_schema(schema_context)
            cols = self._extract_columns_from_schema(schema_context)
            question_lower = user_question.lower()
            sql = f"SELECT * FROM {tbl} LIMIT 5;"

            if retrieved_examples:
                adapted = self._adapt_sql_from_example(retrieved_examples[0]["sql"], schema_context)
                if adapted:
                    sql = adapted

            if "new york" in question_lower and not retrieved_examples:
                pk = self._match_column("city", cols)
                sql = f"SELECT * FROM {tbl} WHERE {pk} = 'New York';"
            elif ("starting with" in question_lower or "starts with" in question_lower) and not retrieved_examples:
                m = re.search(r"starting with ['\"]?(\w)['\"]?", question_lower)
                if not m:
                    m = re.search(r"starts with ['\"]?(\w)['\"]?", question_lower)
                prefix = m.group(1).upper() if m else ""
                target_col = self._match_column("name", cols) if "name" in question_lower else (cols[0] if cols else "*")
                sql = f"SELECT * FROM {tbl} WHERE {target_col} LIKE '{prefix}%';"

            return {
                "sql": sql,
                "explanation": "Mock SQL generated for local testing.",
                "confidence": 0.95,
                "rag_mode": "mock",
            }

        if not self.model:
            raise RuntimeError("Gemini API client is not configured.")

        prompt = self._build_rag_prompt(schema_context, user_question, retrieved_examples)

        try:
            response = await asyncio.wait_for(
                self.model.generate_content_async(
                    prompt,
                    generation_config={
                        "response_mime_type": "application/json",
                        "temperature": 0.0,
                    },
                ),
                timeout=25.0
            )
            raw_text = response.text.strip()
            result = json.loads(raw_text)
            if not isinstance(result, dict) or "sql" not in result:
                raise ValueError("Response missing required keys (sql, explanation, confidence).")
            result.setdefault("explanation", "Adapted from retrieved SQL examples.")
            result.setdefault("confidence", 0.8)
            result["rag_mode"] = "llm_adapt"
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
        await session.execute(text(f"SET LOCAL search_path TO {schema_name}, public"))

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
                    elif isinstance(val, Decimal):
                        row_dict[key] = float(val)
                    elif isinstance(val, uuid.UUID):
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
