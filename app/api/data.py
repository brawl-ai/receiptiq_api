import csv
import io
import pprint
from uuid import UUID
from typing import List, Dict
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, status

from app.models import FieldType, User, Project
from app.depends import require_scope, get_db
from app import crud
from app.models.data import DataValue
from app.models.fields import Field
from app.models.receipts import Receipt
from app.schemas import FieldResponse

router = APIRouter(prefix="/projects/{project_id}/data", tags=["Receipts"])

@router.get("", response_model=List[Dict])
async def get_project_data(
    project_id: UUID,
    current_user: User= Depends(require_scope("read:data")),
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
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access data in this project"
        )
    
    def get_extracted_data(fields: List[Field],  receipt: Receipt):
        data = {}
        for field in fields:
            if field["type"].value == "object":
                data[field["name"]] = get_extracted_data(field["children"], receipt)
            else:
                data_value = db.execute(select(DataValue).where(DataValue.field_id == field["id"], DataValue.receipt_id == receipt.id)).scalar_one_or_none()
                if data_value:
                    data[field["name"]] = {"value": data_value.value,"type": field["type"].value,"description": field["description"]}
        return data

    receipt_data = []
    for receipt in project.receipts:
        fields = [FieldResponse.model_validate(field).model_dump() for field in project.fields if not field.parent]
        extracted_data = get_extracted_data(fields, receipt)
        receipt_data.append({
            "receipt_id": receipt.id,
            "receipt_path": receipt.file_path,
            "data": extracted_data
        })
    return receipt_data

@router.get("/csv")
async def export_project_data_csv(
    project_id: UUID,
    current_user: User = Depends(require_scope("export:data")),
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
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to export data from this project"
        )
    path: str = f"{project.name}_{project.id}.csv"
    with open(path,mode="w", newline="") as output:
        writer = csv.writer(output, delimiter=',',quotechar='|', quoting=csv.QUOTE_MINIMAL)
        field_names = [f"{field.name}" for field in project.fields if field.type != FieldType.OBJECT]
        writer.writerow(["receipt_id", "receipt_path"] + field_names)
        for receipt in project.receipts:
            field_values = {dv.field.name: dv.value for dv in receipt.data_values}
            row = [str(receipt.id), receipt.file_path]
            row.extend(field_values.get(field_name, "") for field_name in field_names)
            writer.writerow(row)
    return {
        "url": path
    }