from uuid import UUID
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import ListResponse
from app.depends import get_db, get_query_params, require_scope
from app.models import User, Field, Project
from app.schemas import AddFieldRequest, UpdateFieldRequest, FieldResponse
from app import crud

router = APIRouter(prefix="/projects/{project_id}/fields", tags=["Fields"])

@router.post("/", response_model=FieldResponse)
async def add_field(
    project_id: UUID,
    field_in: AddFieldRequest,
    current_user: User = Depends(require_scope("write:fields")),
    db: Session = Depends(get_db),
):
    """
        Add a new field to a schema
    """
    project: Project = await crud.get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify schemas in this project"
        )
    field = project.add_field(
        db=db,
        name=field_in.name,
        type=field_in.type,
        description=field_in.description
    )
    return field

@router.post("/{field_id}/add_child", response_model=FieldResponse)
async def add_child_field(
    project_id: UUID,
    field_id: UUID,
    field_in: AddFieldRequest,
    current_user: User = Depends(require_scope("write:fields")),
    db: Session = Depends(get_db),
):
    """
        Add a new field to a schema
    """
    project: Project = await crud.get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify schemas in this project"
        )
    parent: Field = await crud.get_obj_or_404(
        db=db,
        model=Field,
        id=field_id
    )
    field = project.add_field(
        db=db,
        name=field_in.name,
        type=field_in.type,
        description=field_in.description,
        parent_id=parent.id
    )
    return field

@router.get("/", response_model=ListResponse)
async def list_fields(
    project_id: UUID,
    params: Dict[str, Any] = Depends(get_query_params),
    current_user: User = Depends(require_scope("read:fields")),
    db: Session = Depends(get_db)
):
    """
        List all fields in a project's schema
    """
    project: Project = await crud.get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access fields in this project"
        )
    params["project_id"] = project_id
    return await crud.paginate(
        db=db,
        model=Field,
        schema=FieldResponse,
        **params
    )

@router.get("/{field_id}", response_model=FieldResponse)
async def get_field(
    project_id: UUID,
    field_id: UUID,
    current_user: User = Depends(require_scope("read:fields")),
    db: Session = Depends(get_db)
):
    """
        Get a specific field in a project's schema
    """
    project: Project = await crud.get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access fields in this project"
        )
    field = project.get_field(db, field_id)    
    return field

@router.put("/{field_id}", response_model=FieldResponse)
async def update_field(
    project_id: UUID,
    field_id: UUID,
    field_update_in: UpdateFieldRequest,
    current_user: User = Depends(require_scope("write:fields")),
    db: Session = Depends(get_db)
):
    """
        Update a field in a project's schema
    """
    project: Project = await crud.get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify schemas in this project"
        )
    field: Field = project.get_field(db, field_id)
    update_dict = field_update_in.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        if key == "parent_id" and value:
            await crud.get_obj_or_404(db=db,model=Field,id=value)
        setattr(field, key, value)
    db.commit()
    db.refresh(field)
    return field

@router.delete("/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_field_from_project(
    project_id: UUID,
    field_id: UUID,
    current_user: User = Depends(require_scope("delete:fields")),
    db: Session = Depends(get_db)
):
    """
        Delete a field from a project
    """
    project: Project = await crud.get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to this project's fields"
        )
    field = project.get_field(db, field_id)
    db.delete(field)
    db.commit()
    return None