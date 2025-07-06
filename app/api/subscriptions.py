from uuid import UUID
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import ListResponse
from app.depends import get_current_active_verified_user, get_db, get_query_params, require_scope
from app.models import SubscriptionPlan, User, Field, Project
from app.schemas import AddFieldRequest, UpdateFieldRequest, FieldResponse
from app import crud
from app.schemas import SubscriptionPlanResponse

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])

@router.get("/plans", response_model=ListResponse)
async def list_plans(
    params: Dict[str, Any] = Depends(get_query_params),
    db: Session = Depends(get_db),
):
    """
        List subscription plans
    """
    return await crud.paginate(
        db=db,
        model=SubscriptionPlan,
        schema=SubscriptionPlanResponse,
        **params
    )