from uuid import UUID
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict, computed_field

from schemas.fields import FieldResponse
from schemas.data import DataValueResponse
from utils.helpers import get_current_request

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
    data_values: List[DataValueResponse]
    file_path: str
    file_name: str
    mime_type: str
    status: str

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

class ProjectResponse(ProjectBase):
    id: UUID
    receipts: List[ProjectReceipt]
    fields: List[FieldResponse]
    owner: ProjectOwner
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)