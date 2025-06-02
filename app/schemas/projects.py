from datetime import datetime
from typing import List, Optional, Any, Dict
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from app.models.projects import FieldType
from .auth import UserBase

class FieldBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    field_type: FieldType
    description: Optional[str] = Field(None, max_length=500)

class FieldCreate(FieldBase):
    pass

class FieldResponse(FieldBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class SchemaBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)

class SchemaCreate(SchemaBase):
    fields: Optional[List[FieldCreate]] = None

class SchemaResponse(SchemaBase):
    id: UUID
    fields: List[FieldResponse]
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class DataValueBase(BaseModel):
    value: Dict[str, Any] = Field(..., description="The actual value stored in a flexible format")

class DataValueCreate(DataValueBase):
    field_id: UUID

class DataValueResponse(DataValueBase):
    id: UUID
    field: FieldResponse
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ReceiptBase(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    mime_type: str = Field(..., min_length=1, max_length=100)

class ReceiptCreate(ReceiptBase):
    schema_id: UUID

class ReceiptUpdate(BaseModel):
    status: Optional[str] = Field(None, choices=['pending', 'processing', 'completed', 'failed'])
    error_message: Optional[str] = Field(None, max_length=500)

class ReceiptResponse(ReceiptBase):
    id: UUID
    schema: SchemaResponse
    file_path: str
    status: str
    error_message: Optional[str] = None
    data_values: List[DataValueResponse] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)

class ProjectResponse(ProjectBase):
    id: UUID
    schema: Optional[SchemaResponse]
    receipts: List[ReceiptResponse]
    owner: UserBase
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

# Request/Response models for specific operations
class AddFieldToSchemaRequest(BaseModel):
    field_name: str = Field(..., min_length=1, max_length=100)
    field_type: FieldType
    description: Optional[str] = Field(None, max_length=500)

class CreateDataValueRequest(BaseModel):
    field_id: UUID
    value: Dict[str, Any] = Field(..., description="The actual value stored in a flexible format")

class SchemaWithFieldsResponse(SchemaResponse):
    project_id: UUID

class ReceiptWithDataResponse(ReceiptResponse):
    """
    Extended receipt response that includes all data values and their fields
    """
    pass

class ReceiptStatusUpdate(BaseModel):
    status: str = Field(..., choices=['pending', 'processing', 'completed', 'failed'])
    error_message: Optional[str] = Field(None, max_length=500)

class ReceiptDataValueUpdate(BaseModel):
    field_name: str = Field(..., min_length=1, max_length=100)
    value: Dict[str, Any] = Field(..., description="The actual value stored in a flexible format")
