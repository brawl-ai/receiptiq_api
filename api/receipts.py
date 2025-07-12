import io
from typing import Any, Dict
from uuid import UUID
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from models import User, Project, Receipt
from schemas import ReceiptResponse, ReceiptUpdate, ListResponse
from utils import get_obj_or_404, paginate, get_db, get_query_params, require_scope, require_subscription, StorageService

router = APIRouter(prefix="/projects/{project_id}/receipts", tags=["Receipts"])

@router.post("/", response_model=ReceiptResponse)
async def create_receipt(
    project_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_subscription("write:receipts")),
    db: Session = Depends(get_db)
):
    """
    Create a new receipt in a project
    """
    project: Project = await get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create receipts in this project"
        )
    
    allowed_types = ["image/jpeg", "image/png", "image/gif", "application/pdf"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only JPEG, PNG, GIF, and PDF files are allowed."
        )
    
    max_size = 10 * 1024 * 1024  # 10MB
    file_content = await file.read()
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 10MB."
        )
    try:
        storage = StorageService()
        file_path = storage.upload_receipt(project_id=project.id, file=io.BytesIO(file_content), filename=file.filename)
        receipt: Receipt = project.add_receipt(
            db=db,
            file_path=file_path,
            file_name=f"{file.filename}",
            mime_type=file.content_type
        )
        return receipt
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {str(e)}"
        )

@router.get("/", response_model=ListResponse)
async def list_receipts(
    project_id: UUID,
    params: Dict[str, Any] = Depends(get_query_params),
    current_user: User = Depends(require_scope("read:receipts")),
    db: Session = Depends(get_db)
):
    """
    List all receipts in a project, optionally filtered by status
    """
    project: Project = await get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access receipts in this project"
        )
    params["project_id"] = project_id
    return await paginate(
        db=db,
        model=Receipt,
        schema=ReceiptResponse,
        **params
    )

@router.get("/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    project_id: UUID,
    receipt_id: UUID,
    current_user: User = Depends(require_scope("read:receipts")),
    db: Session = Depends(get_db)
):
    """
    Get a specific receipt by ID in a project
    """
    project: Project = await get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access receipts in this project"
        )
    receipt: Receipt = await get_obj_or_404(
        db=db,
        model=Receipt,
        id=receipt_id
    )
    if receipt not in project.receipts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found in this project"
        )
    return receipt

@router.put("/{receipt_id}/", response_model=ReceiptResponse)
async def update_receipt(
    project_id: UUID,
    receipt_id: UUID,
    status_update: ReceiptUpdate,
    current_user: User = Depends(require_subscription("write:receipts")),
    db: Session = Depends(get_db)
):
    """
    Update a receipt's status
    """
    project: Project = await get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update receipts in this project"
        )
    receipt: Receipt = await get_obj_or_404(
        db=db,
        model=Receipt,
        id=receipt_id
    )
    if receipt not in project.receipts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found in this project"
        )
    if status_update.status not in ["pending", "processing", "completed", "failed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status update"
        )
    receipt.status = status_update.status
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return receipt