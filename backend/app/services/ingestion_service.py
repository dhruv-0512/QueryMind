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


def safe_identifier(name: str) -> str:
    """Sanitize a string into a safe PostgreSQL identifier."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    cleaned = re.sub(r"^[^a-zA-Z]+", "", cleaned)
    return cleaned.lower()[:63] if cleaned else "unknown"


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


async def extract_pg_ddl(session: AsyncSession, schema_name: str, table_name: str) -> str:
    """Extract DDL for a table from PostgreSQL using pg_dump style generation."""
    safe_schema = safe_identifier(schema_name)
    safe_table = safe_identifier(table_name)

    # Get columns
    cols_result = await session.execute(
        text(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :tbl
            ORDER BY ordinal_position
        """
        ),
        {"schema": safe_schema, "tbl": safe_table},
    )
    cols = cols_result.fetchall()

    col_lines = []
    for row in cols:
        col_name = row[0]
        data_type = row[1]
        nullable = row[2] == "YES"
        default = row[3]
        line = f'  "{col_name}" {data_type}'
        if not nullable:
            line += " NOT NULL"
        if default:
            line += f" DEFAULT {default}"
        col_lines.append(line)

    ddl = f'CREATE TABLE "{safe_schema}"."{safe_table}" (\n' + ",\n".join(col_lines) + "\n);"
    return ddl


async def extract_pg_schema_metadata(
    session: AsyncSession, schema_name: str, table_name: str
) -> Dict[str, Any]:
    """Extract table metadata (columns, types) from PostgreSQL for embeddings."""
    safe_schema = safe_identifier(schema_name)
    safe_table = safe_identifier(table_name)

    cols_result = await session.execute(
        text(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :tbl
            ORDER BY ordinal_position
        """
        ),
        {"schema": safe_schema, "tbl": safe_table},
    )
    cols = cols_result.fetchall()

    columns = []
    for row in cols:
        columns.append(
            {
                "name": row[0],
                "type": row[1],
                "notnull": row[2] == "NO",
                "pk": False,
                "default_value": None,
            }
        )

    return {
        table_name: {
            "columns": columns,
            "foreign_keys": [],
            "indexes": [],
            "ddl": await extract_pg_ddl(session, schema_name, table_name),
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
    """Generate the temp schema name: user_{user_id}_{db_id}"""
    safe_user = safe_identifier(user_id)
    safe_db = safe_identifier(db_id)
    return f"user_{safe_user}_{safe_db}"


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

        # Convert non-serializable types
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
