from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import List
from app.extractor import InvoiceExtractor
from app.models.projects import Project, Schema, Field, DataValue, Receipt, FieldType
from app.schemas.projects import (
    ProjectCreate, ProjectResponse, ProjectUpdate,
    SchemaCreate, SchemaResponse,
    FieldCreate, FieldResponse,
    DataValueCreate, DataValueResponse,
    ReceiptCreate, ReceiptResponse, ReceiptUpdate,
    AddFieldToSchemaRequest, CreateDataValueRequest,
    SchemaWithFieldsResponse, ReceiptWithDataResponse,
    ReceiptStatusUpdate, ReceiptDataValueUpdate
)
from app.depends import get_current_verified_user
from app.models.auth import User
from uuid import UUID
from app.crud import project_service, schema_service, receipt_service
from app.utils import save_upload_file
from app.config import settings

router = APIRouter(prefix="/projects", tags=["projects"])

# Project endpoints
@router.post("", response_model=ProjectResponse)
async def create_project(
    project_in: ProjectCreate,
    current_user: User = Depends(get_current_verified_user)
):
    """
    Create a new project
    """
    project = project_service.create_with_owner(
        owner=current_user,
        name=project_in.name,
        description=project_in.description
    )
    return project

@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    current_user: User = Depends(get_current_verified_user)
):
    """
    List all projects owned by the current user
    """
    return project_service.get_by_owner(current_user.id)

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    current_user: User = Depends(get_current_verified_user)
):
    """
    Get a specific project by ID
    """
    project = project_service.get(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    if project.owner != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this project"
        )
    return project

@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project_in: ProjectUpdate,
    current_user: User = Depends(get_current_verified_user)
):
    """
    Update a project
    """
    project = project_service.get(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    if project.owner != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this project"
        )

    updated_project = project_service.update(
        project_id,
        name=project_in.name,
        description=project_in.description
    )
    return updated_project

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    current_user: User = Depends(get_current_verified_user)
):
    """
    Delete a project
    """
    project = project_service.get(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    if project.owner != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this project"
        )
    project_service.delete(project_id)

@router.post("/{project_id}/schemas", response_model=SchemaResponse)
async def create_schema(
    project_id: UUID,
    schema_in: SchemaCreate,
    current_user: User = Depends(get_current_verified_user)
):
    """
    Create a new schema in a project
    """
    project = project_service.get(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    if project.owner != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create schemas in this project"
        )

    schema = project.add_schema(
        name=schema_in.name,
        description=schema_in.description
    )

    if schema_in.fields:
        for field in schema_in.fields:
            project.add_field_to_schema(
                schema_id=schema.id,
                field_name=field.name,
                field_type=field.field_type,
                description=field.description
            )

    return schema

@router.get("/{project_id}/schemas", response_model=List[SchemaResponse])
async def list_schemas(
    project_id: UUID,
    current_user: User = Depends(get_current_verified_user)
):
    """
    List all schemas in a project
    """
    project = project_service.get(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    if project.owner != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access schemas in this project"
        )
    return schema_service.get_by_project(project_id)

@router.post("/{project_id}/schemas/{schema_id}/fields", response_model=FieldResponse)
async def add_field_to_schema(
    project_id: UUID,
    schema_id: UUID,
    field_in: AddFieldToSchemaRequest,
    current_user: User = Depends(get_current_verified_user)
):
    """
    Add a new field to a schema
    """
    project = project_service.get(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    if project.owner != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify schemas in this project"
        )

    field = project.add_field_to_schema(
        schema_id=schema_id,
        field_name=field_in.field_name,
        field_type=field_in.field_type,
        description=field_in.description
    )
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schema not found"
        )
    return field

# Receipt endpoints
@router.post("/{project_id}/receipts", response_model=ReceiptResponse)
async def create_receipt(
    project_id: UUID,
    schema_id: UUID = None,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_verified_user)
):
    """
    Create a new receipt in a project
    """
    project: Project = project_service.get(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    if project.owner != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create receipts in this project"
        )
    schema: Schema = Schema.objects.get(id=schema_id)
    if not schema or schema not in project.schemas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schema not found in project"
        )

    try:
        file_path, file_name = await save_upload_file(file, project_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {str(e)}"
        )

    receipt = project.create_receipt(
        schema_id=schema.id,
        file_path=file_path,
        file_name=file_name,
        mime_type=file.content_type
    )
    
    return receipt

@router.get("/{project_id}/receipts", response_model=List[ReceiptResponse])
async def list_receipts(
    project_id: UUID,
    status: str = None,
    current_user: User = Depends(get_current_verified_user)
):
    """
    List all receipts in a project, optionally filtered by status
    """
    project: Project = Project.objects.get(id=project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    if project.owner != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access receipts in this project"
        )

    if status:
        return project.get_receipts_by_status(status)
    return project.receipts

@router.put("/{project_id}/receipts/{receipt_id}/status", response_model=ReceiptResponse)
async def update_receipt_status(
    project_id: UUID,
    receipt_id: UUID,
    status_update: ReceiptStatusUpdate,
    current_user: User = Depends(get_current_verified_user)
):
    """
    Update a receipt's status
    """
    project = Project.objects.get(id=project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    if project.owner != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update receipts in this project"
        )

    receipt = Receipt.objects.get(id=receipt_id)
    if not receipt or receipt not in project.receipts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found"
        )

    receipt.update_status(
        status=status_update.status,
        error_message=status_update.error_message
    )
    return receipt

@router.put("/{project_id}/receipts/{receipt_id}/data", response_model=DataValueResponse)
async def update_receipt_data(
    project_id: UUID,
    receipt_id: UUID,
    data_update: ReceiptDataValueUpdate,
    current_user: User = Depends(get_current_verified_user)
):
    """
    Update a receipt's data value
    """
    project = Project.objects.get(id=project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    if project.owner != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update receipt data in this project"
        )

    receipt = Receipt.objects.get(id=receipt_id)
    if not receipt or receipt not in project.receipts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found"
        )

    field = None
    for f in receipt.schema.fields:
        if f.name == data_update.field_name:
            field = f
            break

    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found in schema"
        )

    data_value = receipt.add_data_value(field, data_update.value)
    return data_value 


@router.post("/{project_id}/process", response_model=List[ReceiptResponse])
async def process(
    project_id: UUID,
    current_user: User = Depends(get_current_verified_user)
):
    """
    Process each "pending" receipt in the project
    """
    project: Project = Project.objects.get(id=project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    if project.owner != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update receipt data in this project"
        )
    extractor = InvoiceExtractor(
        llm_provider="openai",  # or "ollama" for local
        model_name="gpt-4.1-nano-2025-04-14",
        api_key=settings.OPENAI_API_KEY
    )
    if len(project.schemas) == 0:
        raise Exception("No schema was found for this project. Please define a schema and fields before continuing")
    schema_fields = project.schemas[0].fields()
    schema = {field.name: {"type": field.field_type, "description": field.description } for field in schema_fields}
    for receipt in project.receipts:
        if receipt.status == "pending":
            receipt.process(extractor, schema)
        
    return project.receipts

