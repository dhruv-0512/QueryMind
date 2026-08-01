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
from app.utils.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.utils.embeddings import is_api_key_configured
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

RAG_DIRECT_THRESHOLD = 0.78

# Circuit breaker for the Gemini API.
# Trips after 5 consecutive failures (timeout, HTTP error, malformed response),
# stays open for 30 seconds (all requests fail fast with CircuitOpenError),
# then allows one half-open trial before fully closing.
# This protects the backend when Gemini is down: instead of every request
# blocking for 25s (the asyncio.wait_for timeout), they fail in <1ms,
# keeping the server responsive for cached queries and non-AI endpoints.
gemini_circuit = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=30.0,
    name="gemini_api",
)

SQL_KEYWORDS = {
    "select", "from", "where", "group", "by", "order", "having", "join",
    "inner", "left", "right", "outer", "on", "as", "and", "or", "not",
    "in", "like", "between", "is", "null", "distinct", "limit", "offset",
    "asc", "desc", "count", "sum", "avg", "max", "min", "case", "when",
    "then", "else", "end", "with", "union", "all", "exists",
}


import httpx

class SqlService:
    def __init__(self) -> None:
        if settings.DEEPSEEK_API_KEY:
            logger.info(f"DeepSeek API configured with model {settings.DEEPSEEK_MODEL}.")
            self.llm_provider = "deepseek"
        elif is_api_key_configured():
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.model = genai.GenerativeModel("gemini-3.5-flash")
            self.llm_provider = "gemini"
            logger.info("Gemini Model gemini-3.5-flash initialized for SQL Service.")
        else:
            logger.warning("No LLM API key configured. SQL service will use mock generation.")
            self.model = None
            self.llm_provider = "mock"

    def _extract_table_from_schema(self, schema_context: str) -> str:
        match = re.search(r'Table:\s*"([^"]+)"', schema_context, re.IGNORECASE)
        if match:
            return match.group(1)
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
            m = re.search(
                r'"([^"]+)"\s+(TEXT|INTEGER|BIGINT|SMALLINT|BOOLEAN|TIMESTAMP|FLOAT|DOUBLE|REAL|NUMERIC|SERIAL|UUID|DATE|VARCHAR|INTERVAL|DOUBLE PRECISION)',
                line,
                re.IGNORECASE,
            )
            if m:
                cols.append(m.group(1))
            else:
                m2 = re.search(
                    r'\b([a-zA-Z0-9_]+)\s+(TEXT|INTEGER|BIGINT|SMALLINT|BOOLEAN|TIMESTAMP|FLOAT|DOUBLE|REAL|NUMERIC|SERIAL|UUID|DATE|VARCHAR|INTERVAL|DOUBLE PRECISION)',
                    line,
                    re.IGNORECASE,
                )
                if m2 and not line.startswith(("CREATE", "PRIMARY", "FOREIGN", "INDEX", ")")):
                    cols.append(m2.group(1))
        return cols

    def _quote_identifier(self, identifier: str) -> str:
        escaped = identifier.replace('"', '""')
        return f'"{escaped}"'

    def _quote_schema_identifiers(self, sql: str, table_name: str, columns: List[str]) -> str:
        quoted = sql
        # Quote table name if needed
        if table_name and " " in table_name:
            quoted = re.sub(rf'(?<!["\w]){re.escape(table_name)}(?!["\w])', f'"{table_name}"', quoted, flags=re.IGNORECASE)
        # Quote each column
        for col in sorted(columns, key=len, reverse=True):
            if not col:
                continue
            if " " in col or not col.isalnum():
                pattern = rf'(?<!["\w]){re.escape(col)}(?!["\w])'
                quoted = re.sub(pattern, f'"{col}"', quoted, flags=re.IGNORECASE)
        return quoted

    def _normalize_string_literals(self, sql: str, columns: List[str]) -> str:
        column_names = {col.lower() for col in columns}

        def replace_double_quoted(match: re.Match) -> str:
            inner = match.group(1)
            if inner.lower() in column_names:
                return match.group(0)
            return "'" + inner.replace("'", "''") + "'"

        return re.sub(r'"([^"]+)"', replace_double_quoted, sql)

    def _match_column(self, keyword: str, available_cols: List[str]) -> Optional[str]:
        kw_lower = keyword.lower()
        # 1. Exact match
        for col in available_cols:
            if col.lower() == kw_lower:
                return col
        # 2. Substring match
        for col in available_cols:
            if kw_lower in col.lower() or col.lower() in kw_lower:
                return col
        return None

    def _adapt_sql_from_example(
        self,
        example_sql: str,
        schema_context: str,
    ) -> Optional[str]:
        """Map retrieved SQL structure onto the user's schema (RAG-first path)."""
        target_table = self._extract_table_from_schema(schema_context)
        schema_cols = self._extract_columns_from_schema(schema_context)
        if not target_table or not schema_cols:
            return None

        adapted = example_sql.strip().rstrip(";")

        from_match = re.search(r"\bFROM\s+[`\"]?\w+[`\"]?", adapted, re.IGNORECASE)
        if from_match:
            adapted = re.sub(
                r"\bFROM\s+[`\"]?\w+[`\"]?",
                f'FROM "{target_table}"',
                adapted,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            return None

        adapted = re.sub(
            r"\bJOIN\s+[`\"]?\w+[`\"]?",
            f'JOIN "{target_table}"',
            adapted,
            flags=re.IGNORECASE,
        )

        tokens = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", adapted))
        col_map = {}
        for token in tokens:
            low = token.lower()
            if low in SQL_KEYWORDS or token.isdigit() or low in ("my_table", "users", "items", "workers"):
                continue
            if low == target_table.lower():
                continue
            mapped = self._match_column(token, schema_cols)
            if not mapped:
                logger.info(f"RAG direct adaptation rejected: identifier '{token}' not present in target schema columns {schema_cols}")
                return None
            col_map[token] = mapped

        for old, new in sorted(col_map.items(), key=lambda x: -len(x[0])):
            replacement = f'"{new}"'
            adapted = re.sub(rf"\b{re.escape(old)}\b", replacement, adapted)

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

        target_table = self._extract_table_from_schema(schema_context)
        schema_cols = self._extract_columns_from_schema(schema_context)
        adapted_sql = self._quote_schema_identifiers(adapted_sql, target_table, schema_cols)

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
        validation_feedback: Optional[str] = None
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
            examples_block = "LOGICAL SQL TEMPLATE EXAMPLES (FOR CLAUSE STRUCTURE ONLY):\n" + "\n\n".join(parts)

        feedback_block = ""
        if validation_feedback:
            feedback_block = f"\nCRITICAL REGENERATION FEEDBACK FROM PREVIOUS ATTEMPT:\n{validation_feedback}\n"

        return f"""LIVE UPLOADED DATABASE SCHEMA (AUTHORITATIVE SOURCE OF TRUTH):
{schema_context}

{examples_block}
{feedback_block}
USER QUESTION:
{user_question}

STRICT SCHEMA GROUNDING RULES:
1. Grounding Rule: The LIVE UPLOADED DATABASE SCHEMA above is the ONLY ground truth.
2. Template Rule: LOGICAL SQL TEMPLATE EXAMPLES are strictly structural references (WHERE, JOIN, GROUP BY, ORDER BY). Do NOT copy table or column names from template examples unless they exist in the live schema!
3. Identifier Rule: Use ONLY table names and column names that explicitly exist in the live schema. Every table name and column name MUST be enclosed in double quotes (e.g., "column_name", "table_name").
4. Unmatched Field Rule: If the user question requests a field or attribute that does NOT exist in the live schema, set "sql": null, "error": "The uploaded database does not contain the requested field.", "confidence": 0.0.
5. Generate valid PostgreSQL SELECT queries only.

Return JSON format:
{{
  "sql": "SELECT ...",
  "explanation": "...",
  "confidence": 0.9,
  "error": null
}}
"""

    async def generate_sql(
        self,
        schema_context: str,
        user_question: str,
        retrieved_examples: List[Dict[str, Any]] = None,
        validation_feedback: Optional[str] = None
    ) -> Dict[str, Any]:
        retrieved_examples = retrieved_examples or []

        # Only use direct RAG template adaptation if no validation feedback is present
        if not validation_feedback:
            rag_result = self._try_rag_direct(schema_context, user_question, retrieved_examples)
            if rag_result:
                return rag_result

        if not is_api_key_configured():
            logger.info("Mock SQL fallback (no LLM key).")
            tbl = self._extract_table_from_schema(schema_context)
            cols = self._extract_columns_from_schema(schema_context)
            question_lower = user_question.lower()
            sql = f'SELECT * FROM "{tbl}" LIMIT 5;'

            if retrieved_examples and not validation_feedback:
                adapted = self._adapt_sql_from_example(retrieved_examples[0]["sql"], schema_context)
                if adapted:
                    sql = adapted

            if "new york" in question_lower and not retrieved_examples:
                pk = self._match_column("city", cols)
                sql = f'SELECT * FROM "{tbl}" WHERE "{pk}" = \'New York\';'
            elif ("starting with" in question_lower or "starts with" in question_lower) and not retrieved_examples:
                m = re.search(r"starting with ['\"]?(\w)['\"]?", question_lower)
                if not m:
                    m = re.search(r"starts with ['\"]?(\w)['\"]?", question_lower)
                prefix = m.group(1).upper() if m else ""
                target_col = self._match_column("email", cols) if "email" in question_lower else (self._match_column("name", cols) if "name" in question_lower else (cols[0] if cols else "*"))
                sql = f'SELECT * FROM "{tbl}" WHERE "{target_col}" LIKE \'{prefix}%\';'

            return {
                "sql": sql,
                "explanation": "Mock SQL generated for local testing.",
                "confidence": 0.95,
                "rag_mode": "mock",
            }

        if self.llm_provider == "deepseek":
            prompt = self._build_rag_prompt(schema_context, user_question, retrieved_examples, validation_feedback)
            headers = {
                "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": settings.DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a specialized SQL adaptation engine that outputs only valid JSON with keys: sql, explanation, confidence, error."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
            }
            try:
                async with httpx.AsyncClient(timeout=12.0) as client:
                    resp = await client.post(f"{settings.DEEPSEEK_BASE_URL}/chat/completions", headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    raw_content = data["choices"][0]["message"]["content"].strip()
                    result = json.loads(raw_content)
                    if "sql" in result:
                        tbl = self._extract_table_from_schema(schema_context)
                        cols = self._extract_columns_from_schema(schema_context)
                        result["sql"] = self._quote_schema_identifiers(result["sql"], tbl, cols)
                    result.setdefault("explanation", "Generated via DeepSeek AI.")
                    result.setdefault("confidence", 0.9)
                    result["rag_mode"] = "deepseek_llm"
                    return result
            except Exception as e:
                logger.error(f"DeepSeek generation error: {e}")
                err_msg = str(e)
                if "429" in err_msg or "quota" in err_msg.lower():
                    tbl = self._extract_table_from_schema(schema_context)
                    cols = self._extract_columns_from_schema(schema_context)
                    if retrieved_examples:
                        adapted = self._adapt_sql_from_example(retrieved_examples[0]["sql"], schema_context)
                        if adapted:
                            adapted = self._quote_schema_identifiers(adapted, tbl, cols)
                            return {
                                "sql": adapted,
                                "explanation": "Adapted from top SQL example (API quota fallback).",
                                "confidence": 0.85,
                                "rag_mode": "fallback_rag",
                            }
                    return {
                        "sql": f"SELECT * FROM {tbl} LIMIT 10;",
                        "explanation": f"Baseline query over {tbl} (API quota fallback).",
                        "confidence": 0.70,
                        "rag_mode": "fallback_schema",
                    }
                raise e

        if not self.model:
            raise RuntimeError("Gemini API client is not configured.")

        prompt = self._build_rag_prompt(schema_context, user_question, retrieved_examples, validation_feedback)

        try:
            # Circuit breaker wraps ONLY the Gemini network call.
            # If Gemini has failed 5 times in a row, this raises
            # CircuitOpenError immediately (<1ms) instead of waiting
            # 25 seconds for another inevitable timeout.
            response = await gemini_circuit.call(
                asyncio.wait_for(
                    self.model.generate_content_async(
                        prompt,
                        generation_config={
                            "response_mime_type": "application/json",
                            "temperature": 0.0,
                        },
                    ),
                    timeout=25.0,
                )
            )
            raw_text = response.text.strip()
            result = json.loads(raw_text)
            if not isinstance(result, dict) or "sql" not in result:
                raise ValueError("Response missing required keys (sql, explanation, confidence).")
            result.setdefault("explanation", "Adapted from retrieved SQL examples.")
            result.setdefault("confidence", 0.8)
            result["rag_mode"] = "llm_adapt"
            return result
        except CircuitOpenError:
            # Let CircuitOpenError propagate — the router translates it to 503
            raise
        except json.JSONDecodeError as je:
            logger.error(f"Failed to parse Gemini JSON: {je}")
            raise ValueError("Gemini returned invalid JSON. Please retry.")
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "quota" in err_msg.lower():
                logger.warning(f"Gemini quota exceeded ({err_msg}). Falling back to template adaptation.")
                tbl = self._extract_table_from_schema(schema_context)
                cols = self._extract_columns_from_schema(schema_context)
                if retrieved_examples:
                    adapted = self._adapt_sql_from_example(retrieved_examples[0]["sql"], schema_context)
                    if adapted:
                        return {
                            "sql": adapted,
                            "explanation": "Adapted from top SQL example (Gemini API quota reached).",
                            "confidence": 0.85,
                            "rag_mode": "fallback_rag",
                        }
                first_col = cols[0] if cols else "*"
                return {
                    "sql": f"SELECT * FROM {tbl} LIMIT 10;",
                    "explanation": f"Generated baseline query over {tbl} (Gemini API quota reached).",
                    "confidence": 0.70,
                    "rag_mode": "fallback_schema",
                }
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
        # PostgreSQL silently truncates unquoted identifiers to 63 chars.
        # Truncate here so SET search_path matches the actual stored schema name.
        safe_schema = schema_name.strip()[:63] if schema_name else "public"
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
