import os
from pprint import pprint
import uuid
import datetime
from typing import List, Optional
from sqlalchemy import String, DateTime, ForeignKey, select
from sqlalchemy.orm import Mapped, mapped_column,relationship,Session
from sqlalchemy.dialects.postgresql import UUID
from typing import Dict, Optional, Any, List
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlalchemy.dialects.postgresql import UUID

from utils import InvoiceExtractor, StorageService
from models import Model
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

    def add_data(self, db: Session, result: Dict = None, row_id: int = 0):
        """
        Add a new data value to the receipt
        """
        for field_name, value in result.items():
            field: Field = db.execute(select(Field).where(Field.project_id == self.project_id, Field.name == field_name)).scalar_one_or_none()
            if field and len(field.children) == 0:
                data_value = db.execute(select(DataValue).where(DataValue.field_id == field.id, DataValue.receipt_id == self.id, DataValue.row == row_id)).scalar_one_or_none()
                if not data_value:
                    data_value = DataValue()
                data_value.field=field
                data_value.receipt=self
                data_value.value=value["value"]
                data_value.row=row_id
                data_value.x=value["coordinates"].get("x",0)
                data_value.y=value["coordinates"].get("y",0)
                data_value.width=value["coordinates"].get("width",0)
                data_value.height=value["coordinates"].get("height",0)
                db.add(data_value)
                db.commit()
                db.refresh(data_value)
            else:
                if isinstance(value, list):
                    for id,item in enumerate(value):
                        self.add_data(db, item, row_id=id)
                else:
                    self.add_data(db, value)
    
    def localize(self):
        temp_local_path = f"temp/{self.file_path}"
        storage = StorageService()
        storage.download_file(self.file_path, temp_local_path)
        return temp_local_path
    
    def delocalize(self):
        temp_local_path = f"temp/{self.file_path}"
        os.remove(temp_local_path)
        
    def process(self, db: Session, extractor: InvoiceExtractor, schema_dict: Dict[str, Any]) -> List[DataValue]:
        """
        Process the receipt using the extractor
        """
        try:
            temp_local_path = self.localize()
            result,metadata = extractor.extract_from_document(
                document_path=temp_local_path,
                schema=schema_dict,
                extraction_instructions="Focus on accuracy for financial amounts and dates."
            )
            self.status = "processing"
            db.add(self)
            db.flush()
            self.add_data(db, result)                
            self.status = "completed"
            db.add(self)
            db.commit()
            db.refresh(self)
            self.delocalize()
            return self.data_values
        
        except Exception as e:
            self.status = "failed"
            self.error_message = str(e)
            db.add(self)
            db.commit()
            db.refresh(self)
            raise e