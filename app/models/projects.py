import uuid
import datetime
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column,relationship,Session
from sqlalchemy.dialects.postgresql import UUID
from typing import Dict, Optional, List
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlalchemy.dialects.postgresql import UUID

from app.models import Model
from .auth import User
from .fields import Field, FieldType
from .receipts import Receipt

class Project(Model):
    __tablename__ = "projects"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(String(500))
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, onupdate=datetime.datetime.now)
    
    owner: Mapped[User] = relationship("User")
    fields: Mapped[List[Field]] = relationship("Field", back_populates="project", cascade="all, delete-orphan")
    receipts: Mapped[List[Receipt]] = relationship("Receipt", back_populates="project", cascade="all, delete-orphan")

    def add_field(self, db: Session, name: str, type: FieldType, description: str = None, parent_id: UUID = None) -> Field:
        """
        Add a new field to the project
        """
        field = Field(
            name=name,
            type=type,
            description=description,
            project=self,
            parent_id=parent_id
        )
        db.add(field)
        db.commit()
        db.refresh(field)
        return field
    
    def get_field(self, db: Session, field_id: uuid.UUID) -> Optional[Field]:
        """
        Get a field by its ID
        """
        field = db.query(Field).filter(Field.id == field_id, Field.project_id == self.id).first()
        if not field:
            raise HTTPException(status_code=404, detail={"message": f"Field with id {field_id} not found in project {self.name}"})
        return field

    def add_receipt(self, db: Session, file_path: str, file_name: str, mime_type: str) -> Receipt:
        """
        Create a new receipt for the project
        """
        receipt = Receipt(
            project=self,
            file_path=file_path,
            file_name=file_name,
            mime_type=mime_type
        )
        db.add(receipt)
        db.commit()
        db.refresh(receipt)
        return receipt

    @property
    def schema(self) -> Dict[str, str]:
        """
        Generate a schema dictionary from the project's fields
        """
        return {field.name: field.type for field in self.fields}