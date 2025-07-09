

from uuid import UUID
from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

from models.fields import FieldType


class AddFieldRequest(BaseModel):
    name: str
    type: FieldType
    description: Optional[str]

class UpdateFieldRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[FieldType] = None
    description: Optional[str] = None
    parent_id: Optional[UUID] = None

class FieldParent(BaseModel):
    id: UUID
    name: str = Field(..., min_length=1, max_length=100)
    type: FieldType

    model_config = ConfigDict(from_attributes=True)

class FieldProject(BaseModel):
    id: UUID
    name: str = Field(..., min_length=1, max_length=100)

    model_config = ConfigDict(from_attributes=True)

class FieldResponse(BaseModel):
    id: UUID
    name: str = Field(..., min_length=1, max_length=100)
    type: FieldType
    description: Optional[str] = Field(None, max_length=500)
    parent: Optional[FieldParent]
    children: List["FieldResponse"]
    project: FieldProject
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)