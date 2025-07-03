import uuid
import datetime
from typing import List, Optional
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column,relationship,Session
from sqlalchemy.dialects.postgresql import UUID
from typing import Dict, Optional, Any, List
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlalchemy.dialects.postgresql import UUID

from app.extractor import InvoiceExtractor
from app.models import Model
from .data import DataValue
from .fields import Field

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
    
    project: Mapped["Project"] = relationship("Project", back_populates="receipts") # type: ignore
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