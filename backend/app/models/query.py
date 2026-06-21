import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Float, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.database import Base

class QueryHistory(Base):
    __tablename__ = "query_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    db_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("database_connections.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[str] = mapped_column(Text, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    execution_time: Mapped[float] = mapped_column(Float, nullable=True)  # in seconds
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # success, failed, rejected
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="queries")
    database = relationship("DatabaseConnection", back_populates="queries")
