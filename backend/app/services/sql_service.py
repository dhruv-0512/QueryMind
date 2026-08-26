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

RAG_DIRECT_THRESHOLD = 0.60

# Circuit breaker for the Gemini API: trips after 5 consecutive failures,
# stays open 30s (fail-fast), then half-open for one trial.
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

    def _extract_all_tables_from_schema(self, schema_context: str) -> List[str]:
        found = re.findall(
            r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:["\w]+\.)?"?(\w+)"?',
            schema_context,
            re.IGNORECASE,
        )
        if found:
            return list(dict.fromkeys(found))
        match = re.findall(r'Table:\s*"([^"]+)"', schema_context, re.IGNORECASE)
        return list(dict.fromkeys(match)) if match else ["my_table"]

    def _extract_table_from_schema(self, schema_context: str, question: Optional[str] = None) -> str:
        tables = self._extract_all_tables_from_schema(schema_context)
        if not tables:
            return "my_table"

        if question:
            q_lower = question.lower()
            # Match exact or singular table name in question
            for tbl in tables:
                tbl_low = tbl.lower()
                if tbl_low in q_lower or (tbl_low.endswith('s') and tbl_low[:-1] in q_lower):
                    return tbl

        return tables[0]

    def _extract_columns_for_table(self, schema_context: str, table_name: str) -> List[str]:
        blocks = re.findall(
            rf'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:["\w]+\.)?"?{re.escape(table_name)}"?[^;]*?\((.*?)\);',
            schema_context,
            re.IGNORECASE | re.DOTALL,
        )
        if blocks:
            return self._extract_columns_from_schema(blocks[0])
        return self._extract_columns_from_schema(schema_context)

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
        if table_name:
            quoted = re.sub(rf'(?<!["\w]){re.escape(table_name)}(?!["\w])', f'"{table_name}"', quoted, flags=re.IGNORECASE)
        # Quote each column
        for col in sorted(columns, key=len, reverse=True):
            if not col:
                continue
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
        for col in available_cols:
            if col.lower() == kw_lower:
                return col
        for col in available_cols:
            if kw_lower in col.lower() or col.lower() in kw_lower:
                return col
        return None

    def _adapt_sql_from_example(
        self,
        example_sql: str,
        schema_context: str,
        question: Optional[str] = None,
    ) -> Optional[str]:
        """Map retrieved SQL structure onto the user's schema (RAG-first path)."""
        # Skip RAG-direct for JOIN queries — can't reliably adapt multi-table patterns
        if re.search(r'\bJOIN\b', example_sql, re.IGNORECASE) and example_sql.lower().count('join') > 0:
            logger.info("RAG direct skipped: example SQL contains JOINs (multi-table adaptation unreliable)")
            return None

        target_table = self._extract_table_from_schema(schema_context, question)
        schema_cols = self._extract_columns_for_table(schema_context, target_table)
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

        # Strip string literals before extracting column identifier tokens so values aren't mistaken for missing columns
        sql_no_literals = re.sub(r"'[^']*'", "''", adapted)
        sql_no_literals = re.sub(r'"[^"]*"', '""', sql_no_literals)

        tokens = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", sql_no_literals))
        col_map = {}
        for token in tokens:
            low = token.lower()
            if low in SQL_KEYWORDS or token.isdigit() or low in ("my_table", "users", "items", "workers", "table"):
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

    NUMERIC_TYPES = {
        "INTEGER", "BIGINT", "SMALLINT", "FLOAT", "DOUBLE",
        "REAL", "NUMERIC", "SERIAL", "DOUBLE PRECISION", "DECIMAL"
    }

    COMPLEXITY_MARKERS = re.compile(
        r'\b('
        r'group\s+by|for\s+each|each\s+|per\s+|by\s+|'
        r'having|join|where|filter|when|whose|with|who|which|'
        r'greater\s+than|higher\s+than|more\s+than|above|'
        r'less\s+than|lower\s+than|below|under|'
        r'delivered|shipped|pending|cancelled|completed|finished|status|'
        r'chennai|mumbai|delhi|new\s+york|bangalore|city|state|country|'
        r'category|electronics|furniture|kitchen|stationery|'
        r'in\s+the|under\s+the|from\s+the|named\s+|called\s+|'
        r'cheapest|most\s+expensive|fastest|slowest|'
        r'most|least|top|bottom|latest|earliest|oldest|newest|'
        r'before|after|between|during|since|'
        r'among|in\s+addition|except|besides|'
        r'percentage|percent|ratio|relative\s+to|share\s+of|'
        r'never|not\s+in|without\s+any|'
        r'\d+\s+(lowest|highest|cheapest|most|least|orders|products|customers|items|sales|records)|'
        r'(lowest|highest|cheapest|most|least)\s+\d+'
        r')\b',
        re.IGNORECASE
    )

    def _extract_column_types_for_table(self, schema_context: str, table_name: str) -> Dict[str, str]:
        col_types: Dict[str, str] = {}
        blocks = re.findall(
            rf'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:["\w]+\.)?"?{re.escape(table_name)}"?[^;]*?\((.*?)\);',
            schema_context,
            re.IGNORECASE | re.DOTALL,
        )
        target_schema = blocks[0] if blocks else schema_context
        for line in target_schema.split("\n"):
            line = line.strip()
            m = re.search(
                r'"([^"]+)"\s+(TEXT|INTEGER|BIGINT|SMALLINT|BOOLEAN|TIMESTAMP|FLOAT|DOUBLE|REAL|NUMERIC|SERIAL|UUID|DATE|VARCHAR|INTERVAL|DOUBLE PRECISION|DECIMAL)',
                line,
                re.IGNORECASE,
            )
            if m:
                col_types[m.group(1).lower()] = m.group(2).upper()
            else:
                m2 = re.search(
                    r'\b([a-zA-Z0-9_]+)\s+(TEXT|INTEGER|BIGINT|SMALLINT|BOOLEAN|TIMESTAMP|FLOAT|DOUBLE|REAL|NUMERIC|SERIAL|UUID|DATE|VARCHAR|INTERVAL|DOUBLE PRECISION|DECIMAL)',
                    line,
                    re.IGNORECASE,
                )
                if m2 and not line.startswith(("CREATE", "PRIMARY", "FOREIGN", "INDEX", ")")):
                    col_types[m2.group(1).lower()] = m2.group(2).upper()
        return col_types

    def _try_direct_single_table_aggregate(
        self,
        schema_context: str,
        user_question: str,
    ) -> Optional[Dict[str, Any]]:
        q_clean = user_question.strip().lower()

        # Guard: Check for complex query keywords or quantity-qualified rankings that must route to LLM
        if self.COMPLEXITY_MARKERS.search(q_clean):
            return None

        # Guard against quantities (e.g. "5 lowest", "top 3", "2 cheapest")
        if re.search(r'\b(\d+|top|bottom|first|last)\s+(lowest|highest|cheapest|most|least|orders|products|items)\b', q_clean) or re.search(r'\b(lowest|highest|cheapest|most|least)\s+\d+\b', q_clean):
            return None

        # 1. Unambiguously identify target table
        all_tables = self._extract_all_tables_from_schema(schema_context)
        if not all_tables:
            return None

        if len(all_tables) == 1:
            target_table = all_tables[0]
        else:
            matching_tables = []
            for tbl in all_tables:
                tbl_low = tbl.lower()
                if tbl_low in q_clean or (tbl_low.endswith('s') and tbl_low[:-1] in q_clean):
                    matching_tables.append(tbl)
            if len(matching_tables) != 1:
                # Ambiguous table reference in multi-table workspace -> route to LLM
                return None
            target_table = matching_tables[0]

        col_types = self._extract_column_types_for_table(schema_context, target_table)
        schema_cols = self._extract_columns_for_table(schema_context, target_table)
        if not schema_cols:
            return None

        # 2. Check for COUNT pattern (table-level count)
        if re.search(r'\b(total\s+(?:number|count)\s+of|count\s+(?:all\s+)?|how\s+many)\b', q_clean) and not re.search(r'\b(average|avg|mean|sum|min|max|lowest|highest)\b', q_clean):
            count_sql = f'SELECT COUNT(*) AS total_{target_table} FROM "{target_table}";'
            logger.info(f"Deterministic direct COUNT matched on '{target_table}'")
            return {
                "sql": count_sql,
                "explanation": f"Calculated total count directly from '{target_table}' using deterministic schema aggregation.",
                "confidence": 0.98,
                "rag_mode": "direct",
            }

        # 3. Detect Aggregate Operation (AVG, SUM, MIN, MAX)
        op = None
        op_func = None
        if re.search(r'\b(average|avg|mean|overall\s+average)\b', q_clean):
            op = "avg"
            op_func = "AVG"
        elif re.search(r'\b(grand\s+total|overall\s+(?:[\w-]+\s+)?(?:amount|value|revenue|spend|sales|cost|spending)|total\s+(?:[\w-]+\s+)?(?:amount|value|revenue|spend|sales|cost|spending|price)|sum(?:\s+of)?|aggregate\s+(?:[\w-]+\s+)?(?:amount|value|revenue|spend|sales|cost))\b', q_clean):
            op = "sum"
            op_func = "SUM"
        elif re.search(r'\b(minimum|min|lowest|smallest)\b', q_clean):
            op = "min"
            op_func = "MIN"
        elif re.search(r'\b(maximum|max|highest|largest|greatest)\b', q_clean):
            op = "max"
            op_func = "MAX"

        if not op or not op_func:
            return None

        # 4. Unambiguously map requested column
        target_col = None
        for col in schema_cols:
            col_low = col.lower()
            if col_low in q_clean or (col_low.endswith('s') and col_low[:-1] in q_clean):
                if target_col is not None and target_col != col:
                    # Multiple matching columns found in question -> Ambiguous -> LLM
                    return None
                target_col = col

        # Synonym fallback if only 1 summable measure column exists in table
        if not target_col:
            numeric_cols = [c for c in schema_cols if col_types.get(c.lower(), "") in self.NUMERIC_TYPES]
            measure_cols = [c for c in numeric_cols if not c.lower().endswith(('_id', '_key', '_pk', '_fk')) and c.lower() != 'id']
            if len(measure_cols) == 1 and re.search(r'\b(amounts?|spendings?|prices?|costs?|revenues?|sales?|vals?|values?|monetary|totals?)\b', q_clean):
                target_col = measure_cols[0]
            elif len(numeric_cols) == 1 and re.search(r'\b(amounts?|spendings?|prices?|costs?|revenues?|sales?|vals?|values?|monetary|totals?)\b', q_clean):
                target_col = numeric_cols[0]

        if not target_col:
            return None

        # 5. Type validation: AVG and SUM require numeric types
        c_type = col_types.get(target_col.lower(), "NUMERIC")
        if op in ("avg", "sum") and c_type not in self.NUMERIC_TYPES:
            return None

        # 6. Generate Clean Deterministic SQL
        sql = f'SELECT {op_func}("{target_col}") AS {op}_{target_col} FROM "{target_table}";'
        logger.info(f"Deterministic direct {op_func} matched on '{target_table}.{target_col}'")
        return {
            "sql": sql,
            "explanation": f"Calculated {op_func} of '{target_col}' on '{target_table}' directly using deterministic schema aggregation.",
            "confidence": 0.98,
            "rag_mode": "direct",
        }

    def _try_rag_direct(
        self,
        schema_context: str,
        user_question: str,
        retrieved_examples: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        # Rule 1 & 3: Never allow direct RAG adaptation if the query contains complex constraints
        # that require joins, filters, groupings, rankings, or subqueries.
        if self.COMPLEXITY_MARKERS.search(user_question):
            logger.info("Complex query markers detected in question. Direct RAG bypassed to ensure full semantic preservation via LLM.")
            return None

        # 1. Deterministic intent matching for clean single-table aggregate queries (Zero-LLM Fast Path)
        direct_agg = self._try_direct_single_table_aggregate(schema_context, user_question)
        if direct_agg:
            return direct_agg

        if not retrieved_examples:
            return None

        target_table = self._extract_table_from_schema(schema_context, user_question)
        schema_cols = self._extract_columns_for_table(schema_context, target_table)

        # 2. Iterate through top retrieved ChromaDB examples ONLY for clean queries with high similarity
        for ex in retrieved_examples[:5]:
            similarity = ex.get("similarity", 0.0)
            # Require high confidence for candidate template adaptation
            if similarity < 0.85:
                continue

            example_sql = ex.get("sql", "")
            # Disallow adapting complex joins or grouped aggregations through simple token substitution
            if re.search(r'\b(JOIN|GROUP\s+BY|HAVING)\b', example_sql, re.IGNORECASE):
                continue

            adapted_sql = self._adapt_sql_from_example(example_sql, schema_context, user_question)
            if not adapted_sql:
                continue

            adapted_sql = self._quote_schema_identifiers(adapted_sql, target_table, schema_cols)

            logger.info(
                f"RAG-direct adaptation successful (similarity={similarity:.2f}): "
                f"'{ex['question'][:60]}...'"
            )
            return {
                "sql": adapted_sql,
                "explanation": (
                    f"Adapted from similar RAG template (similarity {similarity:.0%}): "
                    f"'{ex['question']}'"
                ),
                "confidence": round(min(0.98, max(0.85, similarity + 0.1)), 2),
                "rag_mode": "direct",
            }

        return None

    def _build_rag_prompt(
        self,
        schema_context: str,
        user_question: str,
        retrieved_examples: List[Dict[str, Any]],
        validation_feedback: Optional[str] = None,
        relationship_map: str = ""
    ) -> str:
        examples_block = ""
        if retrieved_examples:
            parts = []
            for i, ex in enumerate(retrieved_examples, 1):
                sim = ex.get("similarity")
                sim_note = f" (similarity: {sim:.0%})" if sim is not None else ""
                raw_sql = ex.get("sql", "")
                anon_sql = re.sub(
                    r'\b(FROM|JOIN)\s+["`]?[\w]+["`]?',
                    r'\1 <your_table>',
                    raw_sql,
                    flags=re.IGNORECASE,
                )
                parts.append(
                    f"Example {i}{sim_note}:\n"
                    f"Question:\n{ex['question']}\n"
                    f"SQL pattern (structural reference only):\n{anon_sql}"
                )
            examples_block = "LOGICAL SQL TEMPLATE EXAMPLES (FOR CLAUSE STRUCTURE ONLY — do NOT copy table/column names):\n" + "\n\n".join(parts)

        feedback_block = ""
        if validation_feedback:
            feedback_block = f"\nCRITICAL REGENERATION FEEDBACK FROM PREVIOUS ATTEMPT:\n{validation_feedback}\n"

        relationship_section = ("\n" + relationship_map + "\n") if relationship_map else ""

        return f"""LIVE UPLOADED DATABASE SCHEMA (AUTHORITATIVE SOURCE OF TRUTH):
{schema_context}
{relationship_section}
{examples_block}
{feedback_block}
USER QUESTION:
{user_question}

STRICT SQL GENERATION & GROUNDING GUIDELINES:
1. Grounding Rule: The LIVE UPLOADED DATABASE SCHEMA above is the ONLY ground truth. Enclose all table and column names in double quotes.
2. Categorical Literal Grounding: When the schema includes '-- Allowed/Sample Values: [...]', map the user's natural phrasing (e.g. 'completed deliveries' -> 'delivered', 'finished orders' -> 'delivered', 'shipped items' -> 'shipped') to the EXACT matching database literal shown. Do NOT invent ungrounded literal values.
3. Scalar Subquery Projection Rule: In comparison subqueries (such as `WHERE amount > (SELECT ...)` or `HAVING SUM(amount) > (SELECT ...)`), the subquery MUST project ONLY the single aggregated scalar column (e.g. `SELECT AVG(amount) FROM ...`), NEVER multiple columns or table `*`.
4. Entity Projection Rule: When asked for "products that...", "customers who...", "find the cheapest product", or "orders with...", select all entity columns (`SELECT *` or `SELECT p.*`) or the relevant entity columns requested by the user.
5. Ranking & Limit Rule: For "N lowest", "N highest", "top N", or "cheapest product", use `ORDER BY <column> ASC/DESC LIMIT N`.
6. Percentage & Ratio Rule: For percentages relative to total revenue or count, use arithmetic `(SUM("amount") * 100.0 / (SELECT SUM("amount") FROM "orders"))` or window function.
7. JOIN & LEFT JOIN Rule: When joining tables, use explicit JOIN ... ON syntax. Reference matching foreign keys in the schema. When the question asks for an entity and an aggregate "for each" (e.g. "list product names and the total quantity sold for each", "all customers and their orders"), use `LEFT JOIN` with `COALESCE(SUM(...), 0)` so that entities with zero related records (e.g. products with 0 sales) remain visible. Use `INNER JOIN` when filtering on joined conditions (e.g. "orders placed by customers from Chennai").

Return JSON format:
{{
  "sql": "SELECT ...",
  "explanation": "...",
  "confidence": 0.95,
  "error": null
}}
"""

    async def generate_sql(
        self,
        schema_context: str,
        user_question: str,
        retrieved_examples: List[Dict[str, Any]] = None,
        validation_feedback: Optional[str] = None,
        relationship_map: str = ""
    ) -> Dict[str, Any]:
        retrieved_examples = retrieved_examples or []

        # Only use direct RAG template adaptation if no validation feedback is present
        if not validation_feedback:
            rag_result = self._try_rag_direct(schema_context, user_question, retrieved_examples)
            if rag_result:
                return rag_result

            # Level 3–8: Semantic Multi-Facet RAG Composition with AST Constraint Gating
            try:
                from app.services.constraint_extraction_service import constraint_extraction_service
                from app.services.rag_composition_service import rag_composition_service

                target_constraints = constraint_extraction_service.extract_query_constraints(
                    user_question, schema_context
                )
                composed_result = rag_composition_service.compose_sql(
                    target_constraints=target_constraints,
                    retrieved_examples=retrieved_examples,
                    schema_context=schema_context,
                    question=user_question,
                )
                if composed_result:
                    return composed_result
            except Exception as e:
                logger.warning(f"RAG composition attempt skipped: {e}")

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
            prompt = self._build_rag_prompt(schema_context, user_question, retrieved_examples, validation_feedback, relationship_map)
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

        prompt = self._build_rag_prompt(schema_context, user_question, retrieved_examples, validation_feedback, relationship_map)

        try:
            # Raises CircuitOpenError immediately if Gemini has failed 5x in a row.
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
        extra_schemas: List[str] = None,
    ) -> Tuple[List[Dict[str, Any]], float]:
        start = time.time()
        # PostgreSQL silently truncates unquoted identifiers to 63 chars.
        # Truncate here so SET search_path matches the actual stored schema name.
        safe_schema = schema_name.strip()[:63] if schema_name else "public"

        # Build search_path including all datasource schemas
        schemas_for_path = [safe_schema]
        if extra_schemas:
            for s in extra_schemas:
                s_safe = s.strip()[:63]
                if s_safe not in schemas_for_path:
                    schemas_for_path.append(s_safe)
        schemas_for_path.append("public")
        search_path_str = ", ".join(schemas_for_path)
        await session.execute(text(f"SET LOCAL search_path TO {search_path_str}"))

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
