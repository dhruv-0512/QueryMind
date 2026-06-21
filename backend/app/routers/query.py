import json
import hashlib
import logging
import time
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.user import User
from app.models.database_connection import DatabaseConnection
from app.models.query import QueryHistory
from app.middleware.auth_middleware import get_current_user
from app.schemas.query import QueryRequest, QueryResponse
from app.services.rag_service import rag_service
from app.services.sql_service import sql_service
from app.services.cache_service import cache_service
from app.services.kafka_service import kafka_service
from app.utils.sql_validator import validate_sql_query
from app.middleware.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["Queries"])

CACHE_TTL = 3600


def get_question_hash(question: str) -> str:
    return hashlib.sha256(question.strip().lower().encode("utf-8")).hexdigest()


@router.post("", response_model=QueryResponse, dependencies=[Depends(rate_limiter)])
async def execute_nl_query(
    request: QueryRequest,
    db_session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify database connection
    db_stmt = select(DatabaseConnection).where(DatabaseConnection.id == request.db_id)
    user_id = current_user.id
    user_role = current_user.role
    if user_role != "admin":
        db_stmt = db_stmt.where(DatabaseConnection.user_id == user_id)

    result = await db_session.execute(db_stmt)
    db_conn = result.scalars().first()
    if not db_conn:
        raise HTTPException(status_code=404, detail="Database not found or access denied.")

    question = request.question
    schema_name = db_conn.schema_name

    # Step 1: Redis cache
    question_hash = get_question_hash(question)
    cache_key = f"query_cache:{request.db_id}:{question_hash}"

    cached_data = await cache_service.get_cache(cache_key)
    if cached_data:
        try:
            cached_json = json.loads(cached_data)
            cached_json["cached"] = True

            await kafka_service.publish_event(
                topic="query-events",
                event_type="CacheHit",
                user_id=str(user_id),
                payload={"db_id": str(request.db_id), "question": question, "sql": cached_json["sql"]}
            )

            history = QueryHistory(
                user_id=user_id,
                db_id=request.db_id,
                question=question,
                generated_sql=cached_json["sql"],
                explanation=cached_json["explanation"],
                confidence=cached_json["confidence"],
                execution_time=cached_json.get("execution_time", 0.0),
                status="success"
            )
            db_session.add(history)
            await db_session.commit()

            logger.info(f"Cache hit for: '{question}' on DB {request.db_id}")
            return cached_json
        except Exception as e:
            logger.error(f"Cache parse error for key {cache_key}: {e}")

    # Step 2: RAG Schema Retrieval
    try:
        t0 = time.time()
        schema_context = await rag_service.retrieve_schema_context(str(request.db_id), question)
        logger.info(f"TIMING RAG retrieval took {time.time() - t0:.3f}s")
    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve database schema context.")

    # Step 3: SQL Generation
    try:
        t0 = time.time()
        gen_result = await sql_service.generate_sql(schema_context, question)
        logger.info(f"TIMING SQL generation took {time.time() - t0:.3f}s")
        sql = gen_result["sql"]
        explanation = gen_result["explanation"]
        confidence = gen_result["confidence"]
    except Exception as e:
        logger.error(f"SQL generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate SQL: {str(e)}")

    # Step 4: SQL Validation
    is_valid, validation_error = validate_sql_query(sql, schema_name)
    if not is_valid:
        await kafka_service.publish_event(
            topic="query-events",
            event_type="QueryRejected",
            user_id=str(user_id),
            payload={"db_id": str(request.db_id), "question": question, "sql": sql, "reason": validation_error}
        )

        history = QueryHistory(
            user_id=user_id,
            db_id=request.db_id,
            question=question,
            generated_sql=sql,
            explanation=explanation,
            confidence=confidence,
            status="rejected",
            error_message=validation_error
        )
        db_session.add(history)
        await db_session.commit()

        raise HTTPException(status_code=400, detail=f"Generated SQL rejected: {validation_error}")

    # Step 5: Execute against PostgreSQL
    try:
        results, latency = await sql_service.execute_pg_query(
            session=db_session,
            schema_name=schema_name,
            sql=sql,
            max_rows=1000,
            timeout=30.0,
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Query execution error: {e}")
        await db_session.rollback()

        history = QueryHistory(
            user_id=user_id,
            db_id=request.db_id,
            question=question,
            generated_sql=sql,
            explanation=explanation,
            confidence=confidence,
            status="failed",
            error_message=error_msg
        )
        db_session.add(history)
        await db_session.commit()

        await kafka_service.publish_event(
            topic="query-events",
            event_type="QueryFailed",
            user_id=str(user_id),
            payload={"db_id": str(request.db_id), "question": question, "sql": sql, "error": error_msg}
        )

        raise HTTPException(status_code=500, detail=f"Query execution failed: {error_msg}")

    # Step 6: Cache + Event + History
    response_payload = {
        "sql": sql,
        "explanation": explanation,
        "confidence": confidence,
        "results": results,
        "execution_time": latency,
        "cached": False,
    }

    try:
        await cache_service.set_cache(cache_key, json.dumps(response_payload), CACHE_TTL)
    except Exception as e:
        logger.error(f"Redis cache write failed: {e}")

    t0 = time.time()
    await kafka_service.publish_event(
        topic="query-events",
        event_type="QueryExecuted",
        user_id=str(user_id),
        payload={
            "db_id": str(request.db_id),
            "question": question,
            "sql": sql,
            "latency_seconds": latency,
            "row_count": len(results),
        }
    )
    logger.info(f"TIMING Kafka publish took {time.time() - t0:.3f}s")

    history = QueryHistory(
        user_id=user_id,
        db_id=request.db_id,
        question=question,
        generated_sql=sql,
        explanation=explanation,
        confidence=confidence,
        execution_time=latency,
        status="success",
    )
    db_session.add(history)
    await db_session.commit()

    return response_payload


@router.get("/history", response_model=list)
async def get_query_history(
    db_session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(QueryHistory).where(QueryHistory.user_id == current_user.id).order_by(QueryHistory.created_at.desc())
    result = await db_session.execute(stmt)
    history_records = result.scalars().all()

    records = []
    for h in history_records:
        records.append({
            "id": str(h.id),
            "db_id": str(h.db_id),
            "question": h.question,
            "sql": h.generated_sql,
            "explanation": h.explanation,
            "confidence": h.confidence,
            "execution_time": h.execution_time,
            "status": h.status,
            "error_message": h.error_message,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        })
    return records
