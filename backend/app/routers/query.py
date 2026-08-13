import re
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
from app.utils.sql_validator import validate_sql_query, suggest_schema_matches
from app.middleware.rate_limiter import rate_limiter
from app.utils.circuit_breaker import CircuitOpenError

logger = logging.getLogger(__name__)


def _qualify_sql_tables(sql: str, schema_name: str, valid_tables: set) -> str:
    """
    Prefix every unqualified table reference in a SQL string with the
    PostgreSQL schema name so the query never depends on search_path.

    FROM "hr"  ->  FROM "user_f42ba477477c427a_c3c898b0c7fd44c9"."hr"
    JOIN employees -> JOIN "user_..."."employees"

    Only replaces identifiers that are actually in valid_tables so we
    never accidentally qualify subquery aliases or CTEs.
    """
    valid_lower = {t.lower(): t for t in valid_tables}

    def _replace(match: re.Match) -> str:
        keyword = match.group(1)          # FROM or JOIN
        maybe_schema = match.group(2)     # present if already schema-qualified
        table_raw = match.group(3).strip('"')  # table name without quotes
        if maybe_schema:                  # already qualified — leave untouched
            return match.group(0)
        canonical = valid_lower.get(table_raw.lower())
        if canonical:
            return f'{keyword} "{schema_name}"."{canonical}"'
        return match.group(0)             # unknown identifier — leave as-is

    # Pattern matches: FROM ["schema".]"table"  or  JOIN ["schema".]"table"
    # Group 1: keyword, Group 2: optional schema prefix, Group 3: table name
    pattern = re.compile(
        r'\b(FROM|JOIN)\s+(?:"([\w]+)"\s*\.\s*)?"?([\w]+)"?',
        re.IGNORECASE,
    )
    return pattern.sub(_replace, sql)

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
    # Per-user cache key prevents cross-tenant cache leakage on shared DBs.
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
    live_tables = live_schema_info.get("tables", {})

    # NEVER fall back to stale ChromaDB schema — that causes the LLM to hallucinate
    # table names from old embeddings. Live schema is authoritative; bail if empty.
    if not live_schema_text or not live_tables:
        logger.error(
            f"[SCHEMA GROUNDING] Live schema is empty for db_id={request.db_id}, schema='{schema_name}'. "
            f"Refusing to fall back to stale ChromaDB schema context — that causes table name hallucination."
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "This database has no tables in PostgreSQL.\n\n"
                "This usually happens when a previous upload failed partway through.\n\n"
                "To fix this:\n"
                "  1. Delete this database from the list.\n"
                "  2. Re-upload your CSV / XLSX / JSON file."
            )
        )

    full_schema_context = live_schema_text
    valid_tables = set(live_tables.keys())

    # Log schema discovery diagnostics
    discovered_tables = list(live_schema_info.get("tables", {}).keys())
    logger.info(
        f"[SCHEMA DISCOVERY RESULT]\n"
        f"  Current Schema : {schema_name}\n"
        f"  Database ID    : {request.db_id}\n"
        f"  User ID        : {user_id}\n"
        f"  Tables         : {discovered_tables if discovered_tables else '(none found)'}"
    )

    # Pipeline instrumentation
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

    # Step 4: SQL Validation & Schema-Aware Recovery
    is_valid, validation_error, invalid_id = validate_sql_query(sql, schema_name, schema_info=live_schema_info)
    logger.info(f"[VALIDATION RESULT] is_valid={is_valid}, error='{validation_error}', invalid_identifier='{invalid_id}'")

    if not is_valid:
        best_match, match_kind, candidates = suggest_schema_matches(invalid_id, live_schema_info, cutoff=0.55)
        
        # High confidence match found: Attempt automatic recovery
        if best_match:
            logger.info(f"[SCHEMA RECOVERY] High confidence match found: '{invalid_id}' -> '{best_match}'. Retrying generation...")
            feedback_msg = (
                f"Invalid {match_kind} '{invalid_id}' detected. "
                f"The correct {match_kind} in the uploaded database schema is '{best_match}'. "
                f"Please regenerate valid SQL using '{best_match}' and only identifiers present in the schema."
            )
            try:
                live_schema_info = await discover_live_schema(db_session, schema_name)
                full_schema_context = live_schema_info.get("formatted_schema", full_schema_context)
                
                gen_result_retry = await sql_service.generate_sql(
                    full_schema_context,
                    question,
                    retrieved_examples,
                    validation_feedback=feedback_msg
                )
                
                sql_retry = gen_result_retry.get("sql", "")
                logger.info(f"[REGENERATED SQL] {sql_retry}")

                is_valid_retry, val_err_retry, invalid_id_retry = validate_sql_query(sql_retry, schema_name, schema_info=live_schema_info)
                logger.info(f"[RE-VALIDATION RESULT] is_valid={is_valid_retry}, error='{val_err_retry}'")

                if is_valid_retry:
                    sql = sql_retry
                    explanation = gen_result_retry.get("explanation", explanation)
                    confidence = gen_result_retry.get("confidence", confidence)
                else:
                    best_match = None  # Fall through to guidance message if retry still failed
            except Exception as retry_err:
                logger.error(f"Recovery attempt error: {retry_err}")
                best_match = None

        # Low confidence match or recovery failed: Return user guidance message
        if not is_valid and not best_match:
            # Handle the case where schema was empty (tables = None) vs identifier not found
            discovered_tables = list(live_schema_info.get("tables", {}).keys())
            if not invalid_id:
                # validate_sql_query returned None for invalid_id — schema was empty
                user_guidance = (
                    f"This database has no tables in PostgreSQL.\n\n"
                    f"This usually happens when a previous upload failed partway through.\n\n"
                    f"To fix this:\n"
                    f"  1. Delete this database from the list.\n"
                    f"  2. Re-upload your CSV / XLSX / JSON file.\n\n"
                    f"(Schema: {schema_name})"
                )
            else:
                # Identifier was extracted correctly but had no match
                candidates_formatted = "\n".join(f"  - {c}" for c in candidates) if candidates else "  (no tables found in schema)"
                user_guidance = (
                    f"I couldn't find a {match_kind} named '{invalid_id}'.\n\n"
                    f"Available {match_kind}s are:\n\n"
                    f"{candidates_formatted}\n\n"
                    f"Did you mean one of these?"
                )
            
            await kafka_service.publish_event(
                topic="query-events",
                event_type="QueryRejected",
                user_id=str(user_id),
                payload={"db_id": str(request.db_id), "question": question, "sql": sql, "reason": user_guidance}
            )

            history = QueryHistory(
                user_id=user_id,
                db_id=request.db_id,
                question=question,
                generated_sql=sql,
                explanation=explanation,
                confidence=confidence,
                status="rejected",
                error_message=user_guidance
            )
            db_session.add(history)
            await db_session.commit()

            raise HTTPException(status_code=400, detail=user_guidance)

    # Qualify every FROM/JOIN table with the schema prefix; can't rely on search_path persisting.
    sql_qualified = _qualify_sql_tables(sql, schema_name, valid_tables)
    if sql_qualified != sql:
        logger.info(f"[SQL QUALIFICATION] Qualified SQL: {sql_qualified}")
    try:
        results, latency = await sql_service.execute_pg_query(
            session=db_session,
            schema_name=schema_name,
            sql=sql_qualified,
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
