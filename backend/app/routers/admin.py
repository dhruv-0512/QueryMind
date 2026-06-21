import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Dict, Any

from app.database import get_db
from app.models.user import User
from app.models.audit import AuditLog
from app.models.query import QueryHistory
from app.middleware.auth_middleware import require_role
from app.schemas.auth import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Operations"])

# Restrict this entire router to the admin role
admin_dependency = Depends(require_role(["admin"]))

@router.get("/users", response_model=List[UserResponse], dependencies=[admin_dependency])
async def list_users(db: AsyncSession = Depends(get_db)):
    """Retrieve list of all registered users."""
    stmt = select(User).order_by(User.created_at.desc())
    result = await db.execute(stmt)
    users = result.scalars().all()
    return users

@router.get("/audit-logs", response_model=List[Dict[str, Any]], dependencies=[admin_dependency])
async def get_audit_logs(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve system audit logs in a paginated format."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    
    records = []
    for log in logs:
        records.append({
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "event_type": log.event_type,
            "payload": log.payload,
            "created_at": log.created_at.isoformat() if log.created_at else None
        })
    return records

@router.get("/stats", response_model=Dict[str, Any], dependencies=[admin_dependency])
async def get_system_stats(db: AsyncSession = Depends(get_db)):
    """
    Calculate platform performance metrics:
    total query counts, cache hit rate, and average latency.
    """
    try:
        # 1. Total Queries (success, failed, rejected in history)
        total_queries = await db.scalar(select(func.count(QueryHistory.id))) or 0
        
        # 2. Avg execution latency for executed queries
        avg_latency = await db.scalar(
            select(func.coalesce(func.avg(QueryHistory.execution_time), 0.0))
            .where(QueryHistory.status == "success")
        ) or 0.0
        
        # 3. Cache Hits vs Executed Queries
        # Count CacheHit and QueryExecuted event types in Audit Logs
        cache_hits = await db.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.event_type == "CacheHit")
        ) or 0
        
        query_executions = await db.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.event_type == "QueryExecuted")
        ) or 0
        
        total_attempts = cache_hits + query_executions
        cache_hit_rate = (cache_hits / total_attempts) if total_attempts > 0 else 0.0

        return {
            "total_queries": total_queries,
            "cache_hits": cache_hits,
            "query_executions": query_executions,
            "cache_hit_rate": round(cache_hit_rate, 4),
            "avg_latency_seconds": round(avg_latency, 4)
        }
    except Exception as e:
        logger.error(f"Error compiling admin statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve database system statistics."
        )
