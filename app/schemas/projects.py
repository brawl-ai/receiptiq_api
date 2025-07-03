from datetime import datetime
from typing import List, Optional, Any, Dict
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from .fields import FieldResponse

class DataValueCreate(BaseModel):
    value: Dict[str, Any] = Field(..., description="The actual value stored in a flexible format")
    field_id: UUID

class DataValueResponse(BaseModel):
    id: UUID
    value: Dict[str, Any] = Field(..., description="The actual value stored in a flexible format")
    field: FieldResponse
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

class ProjectOwner(BaseModel):
    id: UUID
    email: EmailStr
    first_name: str
    last_name: str

    model_config = ConfigDict(from_attributes=True)

class ProjectReceipt(BaseModel):
    id: UUID
    file_path: str
    file_name: str
    mime_type: str
    status: str

class ProjectResponse(ProjectBase):
    id: UUID
    receipts: List[ProjectReceipt]
    owner: ProjectOwner
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class CreateDataValueRequest(BaseModel):
    field_id: UUID
    value: Dict[str, Any] = Field(..., description="The actual value stored in a flexible format")