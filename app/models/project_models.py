import uuid
import datetime
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column,relationship,Session
from sqlalchemy.dialects.postgresql import UUID
from app.models import Model, User
import datetime
import uuid
from typing import Dict, Optional, Any, List
from sqlalchemy import String, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlalchemy.dialects.postgresql import UUID
from enum import Enum as PyEnum
from app.extractor import InvoiceExtractor

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
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, onupdate=datetime.datetime.now)

    project: Mapped["Project"] = relationship("Project", back_populates="fields")
    data_values: Mapped[List["DataValue"]] = relationship("DataValue", back_populates="field", cascade="all, delete-orphan")

    def clean(self):
        """
        Validate that field_type is a valid FieldType
        """
        if self.type not in [t.value for t in FieldType]:
            raise ValueError(f"Invalid field type: {self.type}. Must be one of {[t.value for t in FieldType]}")

class DataValue(Model):
    __tablename__ = "data_values"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    field_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fields.id"))
    receipt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("receipts.id"))
    value: Mapped[Dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, onupdate=datetime.datetime.now)

    field: Mapped[Field] = relationship("Field", back_populates="data_values")
    receipt: Mapped["Receipt"] = relationship("Receipt", back_populates="data_values")

class Receipt(Model):
    __tablename__ = "receipts"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    file_path: Mapped[str] = mapped_column(String(500))
    file_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default='pending')
    error_message: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, onupdate=datetime.datetime.now)
    
    project: Mapped["Project"] = relationship("Project", back_populates="receipts")
    data_values: Mapped[List[DataValue]] = relationship("DataValue", back_populates="receipt", cascade="all, delete-orphan")

    def add_data(self, db: Session, field: Field, value: Any) -> DataValue:
        """
        Add a new data value to the receipt
        """
        data_value = DataValue(
            field=field,
            receipt=self,
            value={'data': value}
        )
        db.add(data_value)
        db.commit()
        db.refresh(data_value)
        return data_value
        
    def process(self, db: Session, extractor: InvoiceExtractor, schema_dict: Dict[str, Any]) -> List[DataValue]:
        """
        Process the receipt using the extractor
        """
        try:
            result = extractor.extract_from_document(
                document_path=self.file_path,
                schema=schema_dict,
                extraction_instructions="Focus on accuracy for financial amounts and dates."
            )            
            self.status = "processing"
            db.add(self)
            db.flush()
            
            for field_name, value in result.items():
                field = None
                for f in self.project.fields:
                    if f.name == field_name:
                        field = f
                        break
                if field:
                    self.add_data(db, field, value)
            self.status = "completed"
            db.add(self)
            db.commit()
            db.refresh(self)
            return self.data_values
        
        except Exception as e:
            self.status = "failed"
            self.error_message = str(e)
            db.add(self)
            db.commit()
            db.refresh(self)
            raise e

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

    def add_field(self, db: Session, field_name: str, field_type: FieldType, description: str = None) -> Field:
        """
        Add a new field to the project
        """
        field = Field(
            name=field_name,
            field_type=field_type.value,
            description=description,
            project=self
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