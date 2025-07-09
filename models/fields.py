import uuid
import datetime
from typing import List, Optional
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column,relationship
from sqlalchemy.dialects.postgresql import UUID
from models import Model
from typing import Optional, List
from sqlalchemy import String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from enum import Enum as PyEnum

class FieldType(str, PyEnum):
    STRING = 'string'
    NUMBER = 'number'
    DATE = 'date'
    BOOLEAN = 'boolean'
    OBJECT = 'object'
    ARRAY = 'array'

class Field(Model):
    __tablename__ = "fields"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(Enum(FieldType))
    description: Mapped[Optional[str]] = mapped_column(String(500))
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("fields.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, onupdate=datetime.datetime.now)

    __table_args__ = (
        UniqueConstraint('name', 'project_id', name='uq_field_name_project'),
    )

    project: Mapped["Project"] = relationship("Project", back_populates="fields") # type: ignore
    parent: Mapped[Optional["Field"]] = relationship("Field", back_populates="children", remote_side=[id])
    children: Mapped[List["Field"]] = relationship("Field", back_populates="parent", cascade="all, delete-orphan")
    data_values: Mapped[List["DataValue"]] = relationship("DataValue", back_populates="field", cascade="all, delete-orphan") # type: ignore

    def clean(self):
        """
        Validate that field_type is a valid FieldType
        """
        if self.type not in [t.value for t in FieldType]:
            raise ValueError(f"Invalid field type: {self.type}. Must be one of {[t.value for t in FieldType]}")
        
    def __str__(self):
        return f"{self.name} {self.type.value}"