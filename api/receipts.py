import io
from typing import Any, Dict
from uuid import UUID
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from models import DataValue, User, Project, Receipt
from schemas import DataValueResponse, ReceiptResponse, ReceiptUpdate, ListResponse
from schemas.data import DataValueUpdate, DataValueCreate
from schemas.fields import FieldResponse
from utils import get_obj_or_404, paginate, get_db, get_query_params, require_scope, require_subscription, StorageService
from utils.extractor import InvoiceExtractor

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
    
    allowed_types = ["image/jpeg", "image/png", "application/pdf"]
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


@router.post("/{receipt_id}/process", response_model=ReceiptResponse)
async def process_receipt(
    project_id: UUID,
    receipt_id: UUID,
    current_user: User = Depends(require_subscription("process:projects")),
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
    if len(project.fields) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no fields defined. Please add fields before processing receipts."
        )
    extractor = InvoiceExtractor(
        llm_provider="openai",
        model_name="gpt-5-mini"
    )
    fields = [FieldResponse.model_validate(field).model_dump() for field in project.fields if not field.parent]
    receipt.process(db=db,extractor=extractor, fields=fields)
    db.refresh(receipt)
    return receipt

@router.delete("/{receipt_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_receipt(
    project_id: UUID,
    receipt_id: UUID,
    current_user: User = Depends(require_subscription("delete:receipts")),
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
    try:
        storage = StorageService()
        is_deleted = storage.delete_receipt(receipt.file_path)
        if not is_deleted:
            raise HTTPException(status_code=500,detail={"message": f"Failed to delete receipt from storage"})
         
        db.delete(receipt)
        db.commit()
        return None
    except Exception as e:
        raise HTTPException(status_code=500,detail={"message": f"{e}"})
 
@router.post("/{receipt_id}/data", response_model=DataValueResponse)
async def add_data_value(
    project_id: UUID,
    receipt_id: UUID,
    data_value_create: DataValueCreate,
    current_user: User= Depends(require_subscription("write:data")),
    db: Session = Depends(get_db)
):
    """
        Add data value
    """
    project: Project = await get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to add/edit data in this project"
        )
    receipt: Receipt = await get_obj_or_404(
        db=db,
        model=Receipt,
        id=receipt_id
    )
    if receipt.project != project:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This receipt does not belong to this project"
        )
    data_value = DataValue()
    data_value.field_id = data_value_create.field_id
    data_value.receipt_id = receipt_id
    data_value.value = data_value_create.value
    db.add(data_value)
    db.commit()
    db.refresh(data_value)
    return data_value


@router.put("/{receipt_id}/data/{data_value_id}", response_model=DataValueResponse)
async def update_project_data(
    project_id: UUID,
    data_value_id: UUID,
    data_value_update: DataValueUpdate,
    current_user: User= Depends(require_subscription("write:data")),
    db: Session = Depends(get_db)
):
    """
        Update data value
    """
    project: Project = await get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access data in this project"
        )
    
    data_value: DataValue = await get_obj_or_404(
        db=db,
        model=DataValue,
        id=data_value_id
    )
    data_value.value = data_value_update.value
    db.add(data_value)
    db.commit()
    db.refresh(data_value)
    return data_value