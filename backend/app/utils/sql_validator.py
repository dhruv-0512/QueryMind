import re
import logging
from typing import Tuple, Dict, Any, Optional
import sqlglot
from sqlglot import exp

logger = logging.getLogger(__name__)

PROHIBITED_KEYWORDS = {
    "drop", "delete", "alter", "truncate", "update", "insert",
    "replace", "create", "grant", "revoke", "attach", "detach", "vacuum"
}

def validate_sql_query(
    sql: str,
    schema_name: str = "",
    schema_info: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str]:
    """
    Validate SQL safety, syntax, and schema grounding for PostgreSQL.
    Returns (is_valid, error_message).
    """
    if not sql or not sql.strip():
        return False, "SQL query is empty."

    query_clean = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    query_clean = re.sub(r'/\*.*?\*/', '', query_clean, flags=re.DOTALL)

    words = re.findall(r'\b\w+\b', query_clean.lower())
    for word in words:
        if word in PROHIBITED_KEYWORDS:
            logger.warning(f"SQL rejected: banned keyword '{word.upper()}'")
            return False, f"Security violation: Query contains prohibited keyword '{word.upper()}'"

    query_trimmed = query_clean.strip().lower()
    if not query_trimmed.startswith("select") and not query_trimmed.startswith("with"):
        return False, "Only SELECT queries or CTEs (WITH ... SELECT) are allowed."

    # Perform AST schema grounding validation if schema_info is provided
    if schema_info and isinstance(schema_info, dict) and "tables" in schema_info:
        tables_dict = schema_info["tables"]
        
        # Normalize valid tables mapping: table_name -> list of lowercased column names
        normalized_schema = {}
        for tbl_name, tbl_meta in tables_dict.items():
            tbl_key = tbl_name.lower()
            if isinstance(tbl_meta, dict):
                cols = tbl_meta.get("columns", [])
            elif isinstance(tbl_meta, list):
                cols = tbl_meta
            else:
                cols = []
            normalized_schema[tbl_key] = [c.lower() for c in cols]

        if not normalized_schema:
            return False, "No tables found in the uploaded database schema."

        try:
            parsed = sqlglot.parse_one(query_clean, read="postgres")
        except Exception as parse_err:
            logger.warning(f"SQL parsing note: {parse_err}")
            return True, ""

        # Extract CTE aliases so CTE names aren't mistaken for missing tables
        cte_names = {c.alias.lower() for c in parsed.find_all(exp.CTE) if c.alias}

        # Check table references
        referenced_tables = set()
        for t_node in parsed.find_all(exp.Table):
            if t_node.name:
                t_name = t_node.name.lower()
                # Ignore system schemas / functions / CTEs
                if t_name in ("information_schema", "pg_catalog") or t_name in cte_names:
                    continue
                referenced_tables.add(t_name)

        for tbl in referenced_tables:
            if tbl not in normalized_schema:
                logger.warning(f"SQL validation error: Table '{tbl}' does not exist in schema. Valid tables: {list(normalized_schema.keys())}")
                return False, f"Invalid schema reference: Table '{tbl}' does not exist in the database schema. Available tables: {list(normalized_schema.keys())}."

        # Build available columns set across all referenced tables
        available_cols = set()
        for tbl in referenced_tables:
            available_cols.update(normalized_schema[tbl])

        # Check column references
        for col_node in parsed.find_all(exp.Column):
            col_name = col_node.name.lower()
            if not col_name or col_name == "*":
                continue

            table_qualifier = col_node.table.lower() if col_node.table else None
            if table_qualifier and table_qualifier in normalized_schema:
                if col_name not in normalized_schema[table_qualifier]:
                    logger.warning(f"SQL validation error: Column '{col_name}' does not exist in table '{table_qualifier}'.")
                    return False, f"Invalid schema reference: Column '{col_name}' does not exist in table '{table_qualifier}'."
            else:
                if available_cols and col_name not in available_cols:
                    logger.warning(f"SQL validation error: Column '{col_name}' does not exist in discovered schema.")
                    return False, f"Invalid schema reference: Column '{col_name}' does not exist in the database schema."

    return True, ""
