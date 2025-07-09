from uuid import UUID
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

class ReceiptCreate(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    mime_type: str = Field(..., min_length=1, max_length=100)

class ReceiptUpdate(BaseModel):
    status: Optional[str] = Field(None, choices=['pending', 'processing', 'completed', 'failed'])
    error_message: Optional[str] = Field(None, max_length=500)

class ReceiptField(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)

class ReceiptData(BaseModel):
    id: UUID
    value: str
    field: ReceiptField

    model_config = ConfigDict(from_attributes=True)

class ReceiptResponse(BaseModel):
    id: UUID
    file_path: str
    file_name: str
    mime_type: str
    status: str
    error_message: Optional[str] = None
    data_values: List[ReceiptData] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
