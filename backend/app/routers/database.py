import json
import logging
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from app.database import get_db
from app.models.user import User
from app.models.database_connection import DatabaseConnection
from app.middleware.auth_middleware import get_current_user
from app.schemas.database import DatabaseResponse, DatabaseUploadResponse
from app.services.schema_service import schema_service
from app.services.rag_service import rag_service
from app.services.kafka_service import kafka_service
from app.services.ingestion_service import (
    safe_identifier,
    read_file_to_dataframe,
    create_temp_schema,
    load_dataframe_to_pg,
    extract_pg_ddl,
    extract_pg_schema_metadata,
    drop_temp_schema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/database", tags=["Databases"])

ALLOWED_EXTENSIONS = {"csv", "xls", "xlsx", "json"}


@router.post("/upload", response_model=DatabaseUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_database(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Accept CSV, XLSX, or JSON. Load into a temp PostgreSQL schema, extract DDL, index embeddings."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format .{ext}. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    db_id = uuid4()
    filename = file.filename

    try:
        df = await read_file_to_dataframe(file_bytes, filename)
    except Exception as e:
        logger.error(f"Failed to parse file {filename}: {e}")
        raise HTTPException(status_code=400, detail=f"Could not parse file: {str(e)}")

    if df.empty:
        raise HTTPException(status_code=400, detail="File has no data rows.")

    schema_name = f"user_{safe_identifier(str(current_user.id))}_{safe_identifier(str(db_id))}"
    table_name = safe_identifier(filename.rsplit(".", 1)[0])

    try:
        # Create schema and load data
        await create_temp_schema(db, schema_name)
        full_tbl = await load_dataframe_to_pg(db, schema_name, table_name, df)
        logger.info(f"Data loaded into {full_tbl}")

        # Extract DDL and metadata
        metadata = await extract_pg_schema_metadata(db, schema_name, table_name)
        ddl = await extract_pg_ddl(db, schema_name, table_name)

        # Build columns JSON
        cols = metadata.get(table_name, {}).get("columns", [])
        columns_json = json.dumps([c["name"] for c in cols])

        # Save to Postgres
        db_conn = DatabaseConnection(
            id=db_id,
            user_id=current_user.id,
            name=filename,
            schema_name=schema_name,
            table_name=table_name,
            columns_json=columns_json,
            row_count=len(df),
            file_format=ext,
        )
        db.add(db_conn)
        await db.commit()
        await db.refresh(db_conn)

        # Generate schema chunks and index in ChromaDB
        chunks = schema_service.generate_ddl_chunks(metadata)
        await rag_service.index_schema(str(db_id), chunks)

        # Publish Kafka event
        await kafka_service.publish_event(
            topic="schema-events",
            event_type="SchemaIndexed",
            user_id=str(current_user.id),
            payload={
                "db_id": str(db_id),
                "name": filename,
                "schema": schema_name,
                "table": table_name,
                "row_count": len(df),
                "columns": [c["name"] for c in cols],
            }
        )

        return {
            "id": db_id,
            "name": filename,
            "message": f"Uploaded {filename} — {len(df)} rows loaded into {schema_name}.{table_name}.",
            "tables": [table_name],
        }

    except Exception as e:
        logger.error(f"Upload failed for {filename}: {e}")
        try:
            await drop_temp_schema(db, schema_name)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/list", response_model=List[DatabaseResponse])
async def list_databases(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(DatabaseConnection).where(DatabaseConnection.user_id == current_user.id)
    result = await db.execute(stmt)
    databases = result.scalars().all()
    return databases


@router.delete("/{id}", status_code=status.HTTP_200_OK)
async def delete_database(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(DatabaseConnection).where(
        DatabaseConnection.id == id,
        DatabaseConnection.user_id == current_user.id
    )
    result = await db.execute(stmt)
    db_conn = result.scalars().first()

    if not db_conn and current_user.role == "admin":
        stmt_admin = select(DatabaseConnection).where(DatabaseConnection.id == id)
        result_admin = await db.execute(stmt_admin)
        db_conn = result_admin.scalars().first()

    if not db_conn:
        raise HTTPException(status_code=404, detail="Database not found.")

    schema_name = db_conn.schema_name

    # Drop the PostgreSQL temp schema
    try:
        await drop_temp_schema(db, schema_name)
    except Exception as e:
        logger.error(f"Error dropping schema {schema_name}: {e}")

    # Remove ChromaDB embeddings
    try:
        await rag_service.delete_schema(str(id))
    except Exception as e:
        logger.error(f"Error deleting ChromaDB entries for {id}: {e}")

    # Remove DB record
    await db.delete(db_conn)
    await db.commit()

    await kafka_service.publish_event(
        topic="schema-events",
        event_type="SchemaDeleted",
        user_id=str(current_user.id),
        payload={"db_id": str(id), "name": db_conn.name}
    )

    return {"detail": f"Database {db_conn.name} and schema {schema_name} deleted."}
