import json
import hashlib
import logging
import time
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import asyncio
from app.database import get_db
from app.models.user import User
from app.models.database_connection import DatabaseConnection
from app.models.query import QueryHistory
from app.middleware.auth_middleware import get_current_user
from app.schemas.query import QueryRequest, QueryResponse
from app.services.rag_service import rag_service
from app.services.sql_service import sql_service
from app.services.sql_example_retrieval_service import sql_example_retrieval_service
from app.services.cache_service import cache_service
from app.services.kafka_service import kafka_service
from app.services.ingestion_service import discover_live_schema
from app.utils.sql_validator import validate_sql_query
from app.middleware.rate_limiter import rate_limiter
from app.utils.circuit_breaker import CircuitOpenError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["Queries"])

# 5-minute TTL — short enough that data re-uploads are reflected quickly,
# long enough to absorb repeated identical queries during a single analysis session.
CACHE_TTL = 300


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
    # Cache key includes user_id for per-user isolation.
    # Without this, user A could see user B's cached results for a shared
    # database, leaking data across tenant boundaries.
    cache_key = f"query_cache:{user_id}:{request.db_id}:{question_hash}"

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

    # Step 2: Live Schema Discovery from information_schema + Parallel RAG Retrieval
    try:
        t0 = time.time()
        live_schema_info, chroma_schema_context, retrieved_examples = await asyncio.wait_for(
            asyncio.gather(
                discover_live_schema(db_session, schema_name),
                rag_service.retrieve_schema_context(str(request.db_id), question),
                sql_example_retrieval_service.retrieve_examples(question, limit=5)
            ),
            timeout=60.0
        )
        logger.info(f"TIMING Parallel retrieval and live schema discovery took {time.time() - t0:.3f}s")
    except asyncio.TimeoutError:
        logger.error("Parallel retrieval timed out after 60s")
        raise HTTPException(status_code=500, detail="Parallel retrieval timed out. Please try again.")
    except Exception as e:
        logger.error(f"Parallel retrieval failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed parallel retrieval: {str(e)}")

    live_schema_text = live_schema_info.get("formatted_schema", "")
    full_schema_context = live_schema_text if live_schema_text else chroma_schema_context

    # Pipeline Instrumentation Logging - Steps 1-5
    logger.info(f"=== PIPELINE INSTRUMENTATION LOGS ===")
    logger.info(f"1. RETRIEVED SCHEMA DOCUMENTS for schema '{schema_name}' (DB {request.db_id}):\n{full_schema_context}")
    logger.info(f"2. RETRIEVED SQL EXAMPLES (ChromaDB sql_examples_collection):\n{json.dumps([{'question': ex.get('question'), 'sql': ex.get('sql')} for ex in retrieved_examples], indent=2)}")
    logger.info(f"3. SIMILARITY SCORES:\n{json.dumps([{'question': ex.get('question'), 'similarity': ex.get('similarity')} for ex in retrieved_examples], indent=2)}")
    
    # Generate prompt preview
    prompt_preview = sql_service._build_rag_prompt(full_schema_context, question, retrieved_examples)
    logger.info(f"4. FINAL PROMPT SENT TO LLM:\n{prompt_preview}")

    # Publish Kafka events for SQL examples retrieval and completion
    await kafka_service.publish_event(
        topic="query-events",
        event_type="SQLExampleRetrieved",
        user_id=str(user_id),
        payload={
            "db_id": str(request.db_id),
            "question": question,
            "examples": retrieved_examples
        }
    )
    await kafka_service.publish_event(
        topic="query-events",
        event_type="RetrievalCompleted",
        user_id=str(user_id),
        payload={
            "db_id": str(request.db_id),
            "question": question,
            "schema_found": bool(full_schema_context),
            "examples_count": len(retrieved_examples)
        }
    )

    # Step 3: SQL Generation & Grounding
    try:
        t0 = time.time()
        gen_result = await sql_service.generate_sql(full_schema_context, question, retrieved_examples)
        logger.info(f"TIMING SQL generation took {time.time() - t0:.3f}s")
    except CircuitOpenError as e:
        logger.warning(f"Circuit breaker open for Gemini: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"SQL generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate SQL: {str(e)}")

    # Handle explicit LLM un-matched field detection
    if gen_result.get("error") and not gen_result.get("sql"):
        field_error_msg = gen_result["error"]
        logger.info(f"[UNMATCHED FIELD REJECTION] {field_error_msg}")
        raise HTTPException(status_code=400, detail=field_error_msg)

    sql = gen_result.get("sql", "")
    explanation = gen_result.get("explanation", "")
    confidence = gen_result.get("confidence", 0.0)

    logger.info(f"5. GENERATED SQL:\n{sql}")

    # Step 4: SQL Validation against Discovered Live Schema
    is_valid, validation_error = validate_sql_query(sql, schema_name, schema_info=live_schema_info)
    logger.info(f"[VALIDATION RESULT] is_valid={is_valid}, error='{validation_error}'")

    # Step 5: Retry once with feedback if validation fails
    if not is_valid:
        logger.warning(f"[RETRY TRIGGERED] SQL validation failed: '{validation_error}'. Rediscovering schema and retrying once...")
        try:
            # Rediscover schema from information_schema
            live_schema_info = await discover_live_schema(db_session, schema_name)
            full_schema_context = live_schema_info.get("formatted_schema", full_schema_context)
            
            gen_result_retry = await sql_service.generate_sql(
                full_schema_context,
                question,
                retrieved_examples,
                validation_feedback=validation_error
            )
            
            if gen_result_retry.get("error") and not gen_result_retry.get("sql"):
                raise HTTPException(status_code=400, detail="The uploaded database does not contain the requested field.")

            sql_retry = gen_result_retry.get("sql", "")
            logger.info(f"[REGENERATED SQL] {sql_retry}")

            is_valid_retry, validation_error_retry = validate_sql_query(sql_retry, schema_name, schema_info=live_schema_info)
            logger.info(f"[RE-VALIDATION RESULT] is_valid={is_valid_retry}, error='{validation_error_retry}'")

            if is_valid_retry:
                sql = sql_retry
                explanation = gen_result_retry.get("explanation", explanation)
                confidence = gen_result_retry.get("confidence", confidence)
            else:
                await kafka_service.publish_event(
                    topic="query-events",
                    event_type="QueryRejected",
                    user_id=str(user_id),
                    payload={"db_id": str(request.db_id), "question": question, "sql": sql_retry, "reason": validation_error_retry}
                )

                history = QueryHistory(
                    user_id=user_id,
                    db_id=request.db_id,
                    question=question,
                    generated_sql=sql_retry,
                    explanation=explanation,
                    confidence=confidence,
                    status="rejected",
                    error_message=validation_error_retry
                )
                db_session.add(history)
                await db_session.commit()

                raise HTTPException(status_code=400, detail="The uploaded database does not contain the requested field.")
        except HTTPException:
            raise
        except Exception as retry_err:
            logger.error(f"Retry attempt error: {retry_err}")
            raise HTTPException(status_code=400, detail="The uploaded database does not contain the requested field.")

    # Step 6: Execute against PostgreSQL
    try:
        results, latency = await sql_service.execute_pg_query(
            session=db_session,
            schema_name=schema_name,
            sql=sql,
            max_rows=1000,
            timeout=30.0,
        )
        logger.info(f"[EXECUTION RESULT] Completed in {latency:.4f}s with {len(results)} rows.")
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
