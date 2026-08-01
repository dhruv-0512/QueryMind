import re
import logging
from typing import Tuple, Dict, Any, Optional, List
import sqlglot
from sqlglot import exp

logger = logging.getLogger(__name__)

PROHIBITED_KEYWORDS = {
    "drop", "delete", "alter", "truncate", "update", "insert",
    "replace", "create", "grant", "revoke", "attach", "detach", "vacuum"
}

import difflib

def suggest_schema_matches(
    invalid_identifier: str,
    schema_info: Dict[str, Any],
    cutoff: float = 0.55
) -> Tuple[Optional[str], str, List[str]]:
    """
    Find fuzzy / semantic candidate for invalid_identifier in schema_info.
    Returns (best_match, match_kind, available_candidates).
    - best_match: name of top matching candidate if similarity >= cutoff, else None.
    - match_kind: 'table' or 'column'.
    - available_candidates: list of all valid table or column names for clear user guidance.
    """
    if not invalid_identifier or not schema_info or "tables" not in schema_info:
        return None, "table", []

    tables_dict = schema_info["tables"]
    table_names = list(tables_dict.keys())
    invalid_lower = invalid_identifier.lower()

    # 1. Match against table names
    table_matches = difflib.get_close_matches(invalid_lower, [t.lower() for t in table_names], n=1, cutoff=cutoff)
    if table_matches:
        best_tbl = next((t for t in table_names if t.lower() == table_matches[0]), table_matches[0])
        return best_tbl, "table", table_names

    # 2. Match against column names
    all_columns = []
    col_to_original = {}
    for tbl, meta in tables_dict.items():
        cols = meta.get("columns", []) if isinstance(meta, dict) else meta
        for c in cols:
            all_columns.append(c.lower())
            col_to_original[c.lower()] = c

    col_matches = difflib.get_close_matches(invalid_lower, all_columns, n=1, cutoff=cutoff)
    if col_matches:
        best_col = col_to_original.get(col_matches[0], col_matches[0])
        return best_col, "column", list(set(col_to_original.values()))

    # 3. Low confidence (no match >= cutoff)
    return None, "table", table_names


def validate_sql_query(
    sql: str,
    schema_name: str = "",
    schema_info: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    Validate SQL safety, syntax, and schema grounding for PostgreSQL.
    Returns (is_valid, error_message, invalid_identifier).
    """
    if not sql or not sql.strip():
        return False, "SQL query is empty.", None

    query_clean = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    query_clean = re.sub(r'/\*.*?\*/', '', query_clean, flags=re.DOTALL)

    words = re.findall(r'\b\w+\b', query_clean.lower())
    for word in words:
        if word in PROHIBITED_KEYWORDS:
            logger.warning(f"SQL rejected: banned keyword '{word.upper()}'")
            return False, f"Security violation: Query contains prohibited keyword '{word.upper()}'", word

    query_trimmed = query_clean.strip().lower()
    if not query_trimmed.startswith("select") and not query_trimmed.startswith("with"):
        return False, "Only SELECT queries or CTEs (WITH ... SELECT) are allowed.", None

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
            return False, "No tables found in the uploaded database schema.", None

        try:
            parsed = sqlglot.parse_one(query_clean, read="postgres")
        except Exception as parse_err:
            logger.warning(f"SQL parsing note: {parse_err}")
            return True, "", None

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
                return False, f"Invalid schema reference: Table '{tbl}' does not exist in the database schema.", tbl

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
                    return False, f"Invalid schema reference: Column '{col_name}' does not exist in table '{table_qualifier}'.", col_name
            else:
                if available_cols and col_name not in available_cols:
                    logger.warning(f"SQL validation error: Column '{col_name}' does not exist in discovered schema.")
                    return False, f"Invalid schema reference: Column '{col_name}' does not exist in the database schema.", col_name

    return True, "", None
