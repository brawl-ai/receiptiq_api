import csv
import io
from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import Any, Dict, List

from sqlalchemy.orm import Session
from app import crud
from app.depends import get_db, get_query_params, require_scope
from app.extractor import InvoiceExtractor
from app.models.projects import Project, Receipt
from app.schemas import ListResponse
from app.schemas.projects import ProjectCreate, ProjectResponse, ProjectUpdate
from app.schemas.receipts import ReceiptResponse, ReceiptUpdate
from app.depends import get_current_verified_user
from app.models import User
from uuid import UUID
from app.utils import save_upload_file
from app.config import settings

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.post("", response_model=ProjectResponse)
async def create_project(
    project_in: ProjectCreate,
    current_user: User = Depends(require_scope("write:projects")),
    db: Session = Depends(get_db)
):
    """
    Create a new project
    """
    project: Project = Project(
        name=project_in.name,
        description=project_in.description,
        owner_id=current_user.id
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project

@router.get("", response_model=ListResponse)
async def list_filter_search_projects(
    params: Dict[str, Any] = Depends(get_query_params),
    current_user: User = Depends(require_scope("read:projects")),
    db: Session = Depends(get_db)
):
    """
        List, Filter and Search all projects owned by the current user or all if admin
    """
    if not current_user.has_scope("admin"):
        params["owner_id"] = current_user.id
    return await crud.paginate(
        db=db,
        model=Project,
        schema=ProjectResponse,
        **params
    )

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    current_user: User = Depends(require_scope("read:projects")),
    db: Session = Depends(get_db)
):
    """
    Get a specific project by ID
    """
    project: Project = await crud.get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this project"
        )
    return project

@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project_update_in: ProjectUpdate,
    current_user: User = Depends(require_scope("write:projects")),
    db: Session = Depends(get_db)
):
    """
    Update a project
    """
    project: Project = await crud.get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this project"
        )
    project.name = project_update_in.name or project.name
    project.description = project_update_in.description or project.description
    db.add(project)
    db.commit()
    db.refresh(project)
    return project

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    current_user: User = Depends(require_scope("delete:projects")),
    db: Session = Depends(get_db),
):
    """
    Delete a project
    """
    project: Project = await crud.get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this project"
        )
    db.delete(project)
    db.commit()
    return None

@router.post("/{project_id}/process", response_model=List[ReceiptResponse])
async def process(
    project_id: UUID,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Process each "pending" receipt in the project
    """
    project: Project = await crud.get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update receipt data in this project"
        )

    if len(project.fields) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no fields defined. Please add fields before processing receipts."
        )
    if  len(project.receipts) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no receipts to process."
        )
    extractor = InvoiceExtractor(
        llm_provider="openai",  # or "ollama" for local
        model_name="gpt-4.1-nano-2025-04-14",
        api_key=settings.openai_api_key
    )
    schema = {field.name: {"type": field.type, "description": field.description } for field in project.fields}
    for receipt in project.receipts:
        if receipt.status == "pending":
            receipt.process(extractor, schema)
        
    return project.receipts

@router.get("/{project_id}/data", response_model=List[Dict])
async def get_project_data(
    project_id: UUID,
    current_user: User= Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
        Download receipt data
    """
    project: Project = await crud.get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access data in this project"
        )
    receipt_data = []
    for receipt in project.receipts:
        receipt_data.append({
            "receipt_id": receipt.id,
            "receipt_path": receipt.file_path,
            "data": [
                {
                    "name": data_value.field.name,
                    "description": data_value.field.description,
                    "value": data_value.value
                } for data_value in receipt.data_values
            ]
        })
    return receipt_data

@router.get("/{project_id}/data/csv")
async def export_project_data_csv(
    project_id: UUID,
    current_user: User = Depends(get_current_verified_user),
    db: Session = Depends(get_db)
):
    """
    Export receipt data as a CSV file
    """
    project: Project = await crud.get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to export data from this project"
        )

    output = io.StringIO()
    writer = csv.writer(output)
    field_names = [field.name for field in project.fields]
    writer.writerow(["receipt_id", "receipt_path"] + field_names)
    for receipt in project.receipts:
        field_values = {dv.field.name: dv.value for dv in receipt.data_values}
        row = [str(receipt.id), receipt.file_path]
        row.extend(field_values.get(field_name, "") for field_name in field_names)
        writer.writerow(row)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=receipt_data_{project_id}.csv"
        }
    ) 