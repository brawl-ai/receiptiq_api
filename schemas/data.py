from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from datetime import datetime

from .fields import FieldResponse

class DataValueCreate(BaseModel):
    value: str = Field(..., description="The actual value stored in a flexible format")
    field_id: UUID

class DataValueUpdate(BaseModel):
    value: Optional[str]
    field_id: Optional[UUID]

class DataValueResponse(BaseModel):
    id: UUID
    value: str = Field(..., description="The actual value stored in a flexible format")
    field: FieldResponse
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)