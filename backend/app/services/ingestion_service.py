import io
import re
import time
import uuid
import logging
from decimal import Decimal
from typing import Tuple, List, Dict, Any
import pandas as pd
import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PG_TYPE_MAP = {
    "int64": "BIGINT",
    "int32": "INTEGER",
    "int16": "SMALLINT",
    "float64": "DOUBLE PRECISION",
    "float32": "REAL",
    "object": "TEXT",
    "bool": "BOOLEAN",
    "datetime64[ns]": "TIMESTAMP",
    "datetime64[us]": "TIMESTAMP",
    "datetime64[ms]": "TIMESTAMP",
    "datetime64[s]": "TIMESTAMP",
    "timedelta64[ns]": "INTERVAL",
}


def safe_identifier(name: Any) -> str:
    """Sanitize a string or value into a safe PostgreSQL identifier.

    - Replaces any non-alphanumeric/underscore character with '_'.
    - Strips any leading digits (column/table names must start with a letter or '_').
    - Truncates to 63 characters (PostgreSQL identifier limit).

    NOTE: Do NOT use this for schema names built from two UUIDs — use
    make_schema_name() instead to stay within the 63-char limit.
    """
    name_str = str(name) if name is not None else "unknown"
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name_str).lower()
    cleaned = re.sub(r"^[_0-9]+", "", cleaned)  # strip leading underscores/digits
    return cleaned[:63] if cleaned else "unknown"


def make_schema_name(user_id: Any, db_id: Any) -> str:
    """Build a deterministic, PostgreSQL-safe schema name from two UUIDs.

    Uses the first 16 hex characters (no hyphens) of each UUID:
      user_<16hex>_<16hex>
    Total length = 5 + 16 + 1 + 16 = 38 characters — well within the 63-char limit.
    """
    uid_hex = re.sub(r"[^a-f0-9]", "", str(user_id).lower())[:16]
    dbid_hex = re.sub(r"[^a-f0-9]", "", str(db_id).lower())[:16]
    return f"user_{uid_hex}_{dbid_hex}"


def pandas_dtype_to_pg(dtype: str) -> str:
    """Map pandas dtype string to PostgreSQL type."""
    return PG_TYPE_MAP.get(str(dtype), "TEXT")


async def create_temp_schema(session: AsyncSession, schema_name: str) -> None:
    """Create a temporary PostgreSQL schema."""
    safe_schema = safe_identifier(schema_name)
    logger.info(f"Creating schema: {safe_schema}")
    await session.execute(text(f"CREATE SCHEMA IF NOT EXISTS {safe_schema}"))
    await session.commit()


async def drop_temp_schema(session: AsyncSession, schema_name: str) -> None:
    """Drop a temporary PostgreSQL schema cascade."""
    safe_schema = safe_identifier(schema_name)
    logger.info(f"Dropping schema: {safe_schema}")
    await session.execute(text(f"DROP SCHEMA IF EXISTS {safe_schema} CASCADE"))
    await session.commit()


async def load_dataframe_to_pg(
    session: AsyncSession,
    schema_name: str,
    table_name: str,
    df: pd.DataFrame,
) -> str:
    """
    Create a table in the temp schema and load the DataFrame rows via COPY.
    Returns the full qualified table name.
    """
    safe_schema = safe_identifier(schema_name)
    safe_table = safe_identifier(table_name)
    full_name = f"{safe_schema}.{safe_table}"

    if df.empty:
        raise ValueError("Uploaded file contains no data rows.")

    df = df.copy()
    df.columns = [safe_identifier(c) for c in df.columns]

    # Build CREATE TABLE DDL
    col_defs = []
    for col in df.columns:
        pg_type = pandas_dtype_to_pg(str(df[col].dtype))
        col_defs.append(f'"{col}" {pg_type}')
    ddl = f'CREATE TABLE IF NOT EXISTS {full_name} (\n  ' + ",\n  ".join(col_defs) + "\n)"

    logger.info(f"Creating table: {full_name}")
    await session.execute(text(ddl))
    await session.commit()

    # Bulk load via PostgreSQL COPY protocol (asyncpg)
    t0 = time.time()

    # Convert DataFrame to list of tuples, replacing NaN/NaT with None
    df = df.replace({np.nan: None, pd.NaT: None})
    # Convert numpy types to native Python types for asyncpg
    rows = []
    for _, row in df.iterrows():
        clean_row = []
        for val in row:
            if val is None:
                clean_row.append(None)
            elif isinstance(val, (np.integer,)):
                clean_row.append(int(val))
            elif isinstance(val, (np.floating,)):
                clean_row.append(float(val))
            elif isinstance(val, (np.bool_,)):
                clean_row.append(bool(val))
            elif isinstance(val, (pd.Timestamp,)):
                clean_row.append(val.to_pydatetime())
            elif isinstance(val, (np.datetime64,)):
                clean_row.append(pd.Timestamp(val).to_pydatetime())
            elif isinstance(val, (bytes,)):
                clean_row.append(val)
            elif isinstance(val, (np.ndarray,)):
                clean_row.append(val.tolist())
            else:
                clean_row.append(val)
        rows.append(tuple(clean_row))

    # Get raw asyncpg connection from the engine for COPY
    async with session.bind.connect() as raw_conn:
        pg_conn = await raw_conn.get_raw_connection()
        pg_conn = pg_conn.driver_connection

        # Use asyncpg COPY for ultra-fast bulk insert
        await pg_conn.copy_records_to_table(
            safe_table,
            records=rows,
            columns=list(df.columns),
            schema_name=safe_schema,
        )

    elapsed = time.time() - t0
    logger.info(f"Loaded {len(df)} rows into {full_name} via COPY in {elapsed:.2f}s ({len(df)/elapsed:.0f} rows/s)")
    return full_name


async def discover_live_schema(session: AsyncSession, schema_name: str) -> Dict[str, Any]:
    """
    Discover all tables, columns, data types, primary keys, and foreign keys in schema_name from information_schema.
    Returns a complete, structured dictionary and formatted string representation for RAG and LLM grounding.
    """
    # PG truncates unquoted identifiers to 63 chars; match that here.
    safe_schema = schema_name.strip()[:63] if schema_name else ""

    logger.info(f"[SCHEMA DISCOVERY] Querying information_schema for schema='{safe_schema}'")

    # 1. Fetch tables
    discovery_sql = "SELECT table_name FROM information_schema.tables WHERE table_schema = :schema AND table_type = 'BASE TABLE' ORDER BY table_name;"
    logger.info(f"[SCHEMA DISCOVERY] SQL: {discovery_sql} | params: schema={safe_schema!r}")

    tbl_result = await session.execute(
        text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = :schema AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """),
        {"schema": safe_schema}
    )
    tables = [r[0] for r in tbl_result.fetchall()]

    logger.info(f"[SCHEMA DISCOVERY] schema='{safe_schema}' → discovered tables: {tables}")
    if not tables:
        logger.warning(
            f"[SCHEMA DISCOVERY] No tables found for schema='{safe_schema}'. "
            f"Attempting fallback: scanning all user_* schemas in PostgreSQL..."
        )
        # Fallback: find the user_* schema with the longest hex-prefix match.
        try:
            all_schemas_result = await session.execute(
                text("""
                    SELECT s.schema_name
                    FROM information_schema.schemata s
                    WHERE s.schema_name LIKE 'user\\_%' ESCAPE '\\'
                    ORDER BY s.schema_name;
                """)
            )
            all_user_schemas = [r[0] for r in all_schemas_result.fetchall()]
            logger.info(f"[SCHEMA DISCOVERY] All user_* schemas in DB: {all_user_schemas}")

            # Extract hex digits from stored name for comparison (strip non-hex chars)
            import re as _re
            stored_hex = _re.sub(r"[^a-f0-9]", "", safe_schema.lower())

            best_schema = None
            best_score = 0
            for candidate in all_user_schemas:
                # Score = length of longest common prefix of hex digits
                candidate_hex = _re.sub(r"[^a-f0-9]", "", candidate.lower())
                score = 0
                for a, b in zip(stored_hex, candidate_hex):
                    if a == b:
                        score += 1
                    else:
                        break
                if score > best_score:
                    best_score = score
                    best_schema = candidate

            logger.info(
                f"[SCHEMA DISCOVERY] Best fallback match: '{best_schema}' "
                f"(hex prefix score={best_score} vs stored hex='{stored_hex[:16]}...')"
            )

            # Only accept a match if it shares at least 8 hex chars (32-bit entropy)
            if best_schema and best_score >= 8:
                logger.info(f"[SCHEMA DISCOVERY] Using fallback schema: '{best_schema}' instead of '{safe_schema}'")
                safe_schema = best_schema

                tbl_result2 = await session.execute(
                    text("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = :schema AND table_type = 'BASE TABLE'
                        ORDER BY table_name;
                    """),
                    {"schema": safe_schema}
                )
                tables = [r[0] for r in tbl_result2.fetchall()]
                logger.info(f"[SCHEMA DISCOVERY] After fallback, tables: {tables}")
            else:
                logger.warning(
                    f"[SCHEMA DISCOVERY] No matching schema found. "
                    f"The data for schema '{safe_schema}' does not exist in PostgreSQL. "
                    f"User must re-upload the database file."
                )
        except Exception as fb_err:
            logger.error(f"[SCHEMA DISCOVERY] Fallback schema search failed: {fb_err}")


    # 2. Fetch columns
    col_result = await session.execute(
        text("""
            SELECT table_name, column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = :schema
            ORDER BY table_name, ordinal_position;
        """),
        {"schema": safe_schema}
    )
    col_rows = col_result.fetchall()

    # 3. Fetch Primary Keys
    pk_result = await session.execute(
        text("""
            SELECT kcu.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = :schema;
        """),
        {"schema": safe_schema}
    )
    pks_by_table = {}
    for r in pk_result.fetchall():
        pks_by_table.setdefault(r[0], []).append(r[1])

    # 4. Fetch Foreign Keys
    fk_result = await session.execute(
        text("""
            SELECT
                kcu1.table_name AS table_name,
                kcu1.column_name AS column_name,
                kcu2.table_name AS foreign_table_name,
                kcu2.column_name AS foreign_column_name
            FROM information_schema.referential_constraints rc
            JOIN information_schema.key_column_usage kcu1
              ON rc.constraint_name = kcu1.constraint_name
              AND rc.constraint_schema = kcu1.table_schema
            JOIN information_schema.key_column_usage kcu2
              ON rc.unique_constraint_name = kcu2.constraint_name
              AND rc.unique_constraint_schema = kcu2.table_schema
            WHERE kcu1.table_schema = :schema;
        """),
        {"schema": safe_schema}
    )
    fks_by_table = {}
    for r in fk_result.fetchall():
        fks_by_table.setdefault(r[0], []).append({
            "column": r[1],
            "foreign_table": r[2],
            "foreign_column": r[3]
        })

    tables_meta = {}
    formatted_chunks = []

    for t in tables:
        t_cols = [c for c in col_rows if c[0] == t]
        pk_cols = pks_by_table.get(t, [])
        fk_list = fks_by_table.get(t, [])

        col_defs = []
        cols_summary = []
        col_name_list = []

        for row in t_cols:
            c_name, c_type, c_nullable, c_default = row[1], row[2], row[3] == "YES", row[4]
            is_pk = c_name in pk_cols
            col_name_list.append(c_name)

            # Sample distinct values for categorical/text columns to ground LLM in exact literals
            sample_vals = []
            c_type_upper = c_type.upper()
            if any(t_name in c_type_upper for t_name in ("TEXT", "VARCHAR", "CHAR")) or c_name.lower() in ("status", "category", "type", "city", "state", "country", "role", "priority", "gender", "tier", "department"):
                try:
                    val_res = await session.execute(
                        text(f'SELECT DISTINCT "{c_name}" FROM {safe_schema}."{t}" WHERE "{c_name}" IS NOT NULL LIMIT 8')
                    )
                    sample_vals = [str(r[0]) for r in val_res.fetchall() if r[0] is not None]
                except Exception as val_err:
                    logger.debug(f"Failed to fetch sample distinct values for {t}.{c_name}: {val_err}")

            def_str = f'"{c_name}" {c_type.upper()}'
            if is_pk:
                def_str += " PRIMARY KEY"
            elif not c_nullable:
                def_str += " NOT NULL"
            if c_default:
                def_str += f" DEFAULT {c_default}"
            if sample_vals:
                def_str += f" -- Allowed/Sample Values: {sample_vals}"

            col_defs.append(f"  {def_str}")
            sample_hint = f", Sample Values: {sample_vals}" if sample_vals else ""
            cols_summary.append(f'    - "{c_name}" ({c_type.upper()}{", PRIMARY KEY" if is_pk else ""}{sample_hint})')

        fk_defs = []
        for fk in fk_list:
            fk_defs.append(f'  FOREIGN KEY ("{fk["column"]}") REFERENCES "{fk["foreign_table"]}"("{fk["foreign_column"]}")')

        table_ddl = f'CREATE TABLE "{t}" (\n' + ",\n".join(col_defs + fk_defs) + "\n);"

        tables_meta[t] = {
            "columns": col_name_list,
            "column_details": [
                {"name": c[1], "type": c[2], "nullable": c[3] == "YES", "pk": c[1] in pk_cols}
                for c in t_cols
            ],
            "primary_keys": pk_cols,
            "foreign_keys": fk_list,
            "ddl": table_ddl
        }

        chunk_text = (
            f'Table: "{t}"\n'
            f'Columns:\n' + "\n".join(cols_summary) + "\n"
        )
        if fk_list:
            chunk_text += "Foreign Keys:\n" + "\n".join([f'  - "{fk["column"]}" -> "{fk["foreign_table"]}"."{fk["foreign_column"]}"' for fk in fk_list]) + "\n"
        chunk_text += f"DDL:\n{table_ddl}"

        formatted_chunks.append({
            "table_name": t,
            "chunk_text": chunk_text,
            "columns": col_name_list,
            "ddl": table_ddl
        })

    full_formatted_schema = "\n\n".join([c["chunk_text"] for c in formatted_chunks])

    return {
        "schema_name": safe_schema,
        "tables": tables_meta,
        "chunks": formatted_chunks,
        "formatted_schema": full_formatted_schema
    }


async def extract_pg_ddl(session: AsyncSession, schema_name: str, table_name: str) -> str:
    """Extract DDL for a table from PostgreSQL using information_schema."""
    discovered = await discover_live_schema(session, schema_name)
    tbl_meta = discovered["tables"].get(table_name)
    if tbl_meta and "ddl" in tbl_meta:
        return tbl_meta["ddl"]
    return f'CREATE TABLE "{table_name}" ();'


async def extract_pg_schema_metadata(
    session: AsyncSession, schema_name: str, table_name: str
) -> Dict[str, Any]:
    """Extract table metadata from PostgreSQL for ChromaDB indexing."""
    discovered = await discover_live_schema(session, schema_name)
    tbl_meta = discovered["tables"].get(table_name, {})
    return {
        table_name: {
            "columns": tbl_meta.get("column_details", []),
            "foreign_keys": tbl_meta.get("foreign_keys", []),
            "primary_keys": tbl_meta.get("primary_keys", []),
            "indexes": [],
            "ddl": tbl_meta.get("ddl", ""),
            "index_ddls": [],
        }
    }


async def read_file_to_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Read uploaded file bytes into a pandas DataFrame."""
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext == "csv":
        return pd.read_csv(io.BytesIO(file_bytes))
    elif ext in ("xls", "xlsx"):
        return pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    elif ext == "json":
        return pd.read_json(io.BytesIO(file_bytes))
    else:
        raise ValueError(f"Unsupported file format: .{ext}")


async def get_temp_schema_name(user_id: str, db_id: str) -> str:
    """Generate the deterministic temp schema name for a user/db pair."""
    return make_schema_name(user_id, db_id)


async def execute_pg_query(
    session: AsyncSession,
    schema_name: str,
    sql: str,
    max_rows: int = 1000,
    timeout: float = 30.0,
) -> Tuple[List[Dict[str, Any]], float]:
    """Execute a SELECT query on the temp schema and return results."""
    import time
    import asyncio

    start = time.time()
    safe_schema = safe_identifier(schema_name)

    # Set search_path so queries work without schema prefix
    await session.execute(text(f"SET LOCAL search_path TO {safe_schema}"))

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
        raise TimeoutError(f"Query execution timed out after {timeout} seconds.")
    except Exception as e:
        logger.error(f"PostgreSQL query execution error: {e}")
        raise e


ingestion_service = None  # functions are module-level, no class needed
