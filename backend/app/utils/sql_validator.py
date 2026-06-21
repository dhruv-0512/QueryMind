import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

PROHIBITED_KEYWORDS = {
    "drop", "delete", "alter", "truncate", "update", "insert",
    "replace", "create", "grant", "revoke", "attach", "detach", "vacuum"
}

def validate_sql_query(sql: str, schema_name: str) -> Tuple[bool, str]:
    """
    Validate SQL safety and syntax for PostgreSQL.
    Returns (is_valid, error_message).
    """
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

    return True, ""
