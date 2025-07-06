import uuid
import datetime
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column,relationship
from sqlalchemy.dialects.postgresql import UUID
from app.models import Model
from typing import Dict, Optional, Any
from sqlalchemy import DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID


class DataValue(Model):
    __tablename__ = "data_values"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    field_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fields.id"))
    receipt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("receipts.id"))
    value: Mapped[str] = mapped_column(String(300),nullable=False)
    x: Mapped[int] = mapped_column(Integer,default=0)
    y: Mapped[int] = mapped_column(Integer,default=0)
    width: Mapped[int] = mapped_column(Integer,default=0)
    height: Mapped[int] = mapped_column(Integer,default=0)
    value: Mapped[str] = mapped_column(String(300),nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, onupdate=datetime.datetime.now)

    field: Mapped["Field"] = relationship("Field", back_populates="data_values") # type: ignore
    receipt: Mapped["Receipt"] = relationship("Receipt", back_populates="data_values") # type: ignore