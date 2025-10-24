from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from models.subscriptions import Payment
from utils import get_obj_or_404, paginate, require_subscription
from schemas import FieldResponse
from utils import get_db, get_query_params, require_scope, InvoiceExtractor
from models.projects import Project, Receipt
from schemas import ListResponse
from schemas.projects import ProjectCreate, ProjectResponse, ProjectUpdate
from schemas.receipts import ReceiptResponse
from models import User
from uuid import UUID
from config import settings

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.post("", response_model=ProjectResponse)
async def create_project(
    project_in: ProjectCreate,
    current_user: User = Depends(require_subscription("write:projects")),
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
    return await paginate(
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
    project: Project = await get_obj_or_404(
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
    current_user: User = Depends(require_subscription("write:projects")),
    db: Session = Depends(get_db)
):
    """
    Update a project
    """
    project: Project = await get_obj_or_404(
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
    current_user: User = Depends(require_subscription("delete:projects")),
    db: Session = Depends(get_db),
):
    """
    Delete a project
    """
    project: Project = await get_obj_or_404(
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

@router.post("/{project_id}/process", response_model=ListResponse)
async def process(
    project_id: UUID,
    params: Dict[str, Any] = Depends(get_query_params),
    current_user: User = Depends(require_subscription("process:projects")),
    db: Session = Depends(get_db)
):
    """
    Process each "pending" receipt in the project
    """
    project: Project = await get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
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
        llm_provider="openai",
        model_name="gpt-5-mini"
    )
    fields = [FieldResponse.model_validate(field).model_dump() for field in project.fields if not field.parent]
    for receipt in project.receipts:
        if receipt.status in ["pending", "completed","failed"]:
            receipt.process(db=db,extractor=extractor, fields=fields)
            # payment: Payment | None = db.execute(select(Payment).where(
            #                             Payment.user_id == current_user.id,
            #                             Payment.subscription_end_at > func.now()  # Check if subscription is active
            #                         )).scalar_one_or_none()
            # payment.invoices_processed += 1
            # db.commit()
    params["project_id"] = project.id
    return await paginate(
        db=db,
        model=Receipt,
        schema=ReceiptResponse,
        **params
    )