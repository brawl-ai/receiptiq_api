from uuid import UUID
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field

from utils.helpers import get_current_request

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
    x: int
    y: int
    width: int
    height: int
    field: ReceiptField

    model_config = ConfigDict(from_attributes=True)

class ReceiptResponse(BaseModel):
    id: UUID
    file_name: str
    mime_type: str
    status: str
    error_message: Optional[str] = None
    data_values: List[ReceiptData] = []
    created_at: datetime
    updated_at: Optional[datetime] = None
    file_path: str

    @computed_field
    @property
    def download_url(self) -> str:
        """Compute the download URL from the current request context"""
        request = get_current_request()
        if request:
            return f"{request.base_url}files/{self.file_path}"
        filename = self.file_path.split('/')[-1] if '/' in self.file_path else self.file_path
        return f"/files/{filename}"

    model_config = ConfigDict(from_attributes=True)