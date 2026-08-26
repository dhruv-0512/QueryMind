import json
import logging
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import asyncio
from typing import List, Optional
from pydantic import BaseModel
from app.services.relationship_inference_service import relationship_inference_service

from app.database import get_db
from app.models.user import User
from app.models.database_connection import DatabaseConnection
from app.middleware.auth_middleware import get_current_user
from app.schemas.database import DatabaseResponse, DatabaseUploadResponse
from app.services.schema_service import schema_service
from app.services.rag_service import rag_service
from app.services.kafka_service import kafka_service
from app.services.cache_service import cache_service
from app.services.ingestion_service import (
    safe_identifier,
    make_schema_name,
    read_file_to_dataframe,
    create_temp_schema,
    load_dataframe_to_pg,
    extract_pg_ddl,
    extract_pg_schema_metadata,
    discover_live_schema,
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

    schema_name = make_schema_name(current_user.id, db_id)
    table_name = safe_identifier(filename.rsplit(".", 1)[0])

    try:
        # Create schema and load data
        await create_temp_schema(db, schema_name)
        full_tbl = await load_dataframe_to_pg(db, schema_name, table_name, df)
        logger.info(f"Data loaded into {full_tbl}")

        # Discover live schema from information_schema
        discovered = await discover_live_schema(db, schema_name)
        tbl_meta = discovered["tables"].get(table_name, {})
        cols = tbl_meta.get("columns", [safe_identifier(c) for c in df.columns])
        columns_json = json.dumps(cols)

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
        await rag_service.index_schema(str(db_id), discovered["chunks"])

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
                "columns": cols,  # already a list of column name strings
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


from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, BackgroundTasks

async def _background_cleanup_deleted_db(db_id: str, schema_name: str, user_id: str, db_name: str):
    """Background task to clean up temp schema, ChromaDB embeddings, Redis cache, and publish audit event."""
    from app.database import SessionLocal
    try:
        async with SessionLocal() as session:
            await drop_temp_schema(session, schema_name)
    except Exception as e:
        logger.error(f"[ASYNC CLEANUP] Error dropping temp schema '{schema_name}': {e}")

    try:
        await rag_service.delete_schema(db_id)
    except Exception as e:
        logger.error(f"[ASYNC CLEANUP] Error deleting ChromaDB schema entries for '{db_id}': {e}")

    try:
        await cache_service.invalidate_db_cache(db_id)
    except Exception as e:
        logger.error(f"[ASYNC CLEANUP] Error invalidating Redis cache for '{db_id}': {e}")

    try:
        await kafka_service.publish_event(
            topic="schema-events",
            event_type="SchemaDeleted",
            user_id=user_id,
            payload={"db_id": db_id, "name": db_name}
        )
    except Exception as e:
        logger.error(f"[ASYNC CLEANUP] Error publishing Kafka event for '{db_id}': {e}")


@router.delete("/{id}", status_code=status.HTTP_200_OK)
async def delete_database(
    id: UUID,
    background_tasks: BackgroundTasks,
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
    db_name = db_conn.name

    # Delete database connection record immediately for sub-10ms response time
    await db.delete(db_conn)
    await db.commit()

    # Schedule schema, ChromaDB, and cache cleanup in background
    background_tasks.add_task(
        _background_cleanup_deleted_db,
        str(id),
        schema_name,
        str(current_user.id),
        db_name
    )

    return {"detail": f"Database '{db_name}' deleted successfully."}


class DetectRelationshipsRequest(BaseModel):
    db_ids: Optional[List[UUID]] = None
    db_id: Optional[UUID] = None


@router.post("/relationships/detect")
async def detect_database_relationships(
    request: DetectRelationshipsRequest,
    db_session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Detect candidate relationships between multiple database tables
    using deterministic schema and data analysis without AI/LLMs.
    """
    ids = request.db_ids or ([request.db_id] if request.db_id else [])
    if not ids:
        raise HTTPException(status_code=400, detail="Either db_id or db_ids must be provided.")

    conns = []
    for did in ids:
        stmt = select(DatabaseConnection).where(DatabaseConnection.id == did)
        if current_user.role != "admin":
            stmt = stmt.where(DatabaseConnection.user_id == current_user.id)
        res = await db_session.execute(stmt)
        conn = res.scalars().first()
        if conn:
            conns.append(conn)

    if not conns:
        return {"candidates": []}

    merged_tables = {}
    for conn in conns:
        try:
            sr = await discover_live_schema(db_session, conn.schema_name)
            if sr and isinstance(sr, dict):
                merged_tables.update(sr.get("tables", {}))
        except Exception as e:
            logger.error(f"Schema discovery failed for conn {conn.id}: {e}")

    schema_info = {"tables": merged_tables}
    candidates = relationship_inference_service.detect_candidate_relationships(schema_info)

    return {"candidates": candidates}
