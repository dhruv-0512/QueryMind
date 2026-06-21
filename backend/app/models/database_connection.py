import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.database import Base

class DatabaseConnection(Base):
    __tablename__ = "database_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(127), nullable=False)
    table_name: Mapped[str] = mapped_column(String(127), nullable=False)
    columns_json: Mapped[str] = mapped_column(Text, nullable=True)
    row_count: Mapped[int] = mapped_column(default=0)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", back_populates="databases")
    queries = relationship("QueryHistory", back_populates="database", cascade="all, delete-orphan")
