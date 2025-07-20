import csv
import io
import os
from uuid import UUID
from typing import List, Dict
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Request, status

from models import FieldType, User, Project
from schemas.data import DataValueResponse, DataValueUpdate
from utils import StorageService, get_obj_or_404, require_scope, get_db, require_subscription
from models.data import DataValue
from models.fields import Field
from models.receipts import Receipt
from schemas import FieldResponse

router = APIRouter(prefix="/projects/{project_id}/data", tags=["Data"])

@router.get("", response_model=List[Dict])
async def get_project_data(
    project_id: UUID,
    current_user: User= Depends(require_scope("read:data")),
    db: Session = Depends(get_db)
):
    """
        Download receipt data
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
    
    def get_extracted_data(fields: List[Field],  receipt: Receipt, row_id: int = 0):
        data = {}
        for field in fields:
            if field["type"].value == "object":
                data[field["name"]] = get_extracted_data(field["children"], receipt)
            if field["type"].value == "array":
                items = []
                rows = db.execute(select(
                        DataValue.row,
                        func.count(DataValue.id),
                        func.array_agg(DataValue.value)
                    ).group_by(DataValue.row)).scalars().all()
                for row in rows:
                    items.append(get_extracted_data(field["children"],receipt, row_id=row))
                data[field["name"]] = items
            else:
                data_value = db.execute(select(DataValue).where(DataValue.field_id == field["id"], DataValue.receipt_id == receipt.id, DataValue.row == row_id)).scalar_one_or_none()
                if data_value:
                    data[field["name"]] = {
                                            "value": data_value.value,
                                            "type": field["type"].value,
                                            "description": field["description"],
                                            "coordinates": {"x": data_value.x,"y":data_value.y,"height": data_value.height, "width":data_value.width}
                                        }
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

def save_csv(project: Project):
    path: str = f"temp/{project.name}_{project.id}.csv"
    data = []
    for receipt in project.receipts:
        row = {
            "receipt_id": str(receipt.id),
            "receipt_path": receipt.file_path
        }
        for dv in receipt.data_values:
            row[dv.fully_name] = dv.value
        data.append(row)
    with open(path,mode="w", newline="") as output:
        writer = csv.writer(output, delimiter=',',quotechar='|', quoting=csv.QUOTE_MINIMAL)
        field_names = [k for k,v in data[0].items()]
        writer.writerow(field_names)
        for r in data:
            writer.writerow([v for k,v in r.items()])
    with open(path,"rb") as f:
        file = io.BytesIO(f.read())
    os.remove(path)
    return file

@router.get("/csv")
async def export_project_data_csv(
    request: Request,
    project_id: UUID,
    current_user: User = Depends(require_subscription("export:data")),
    db: Session = Depends(get_db)
):
    """
    Export receipt data as a CSV file
    """
    project: Project = await get_obj_or_404(
        db=db,
        model=Project,
        id=project_id
    )
    if project.owner != current_user and not current_user.has_scope("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to export data from this project"
        )
    try:
        file = save_csv(project)
        storage = StorageService()
        export_storage_path = storage.upload_export(project_id=project.id,file=file,filename="data_export.csv")
        return {
            "url": f"{request.base_url}files/{export_storage_path}"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save export file: {str(e)}"
        )