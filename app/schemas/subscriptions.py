

from decimal import Decimal
from uuid import UUID
from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

from app.models import CurrencyType, PlanStatus, BillingInterval

class SubscriptionPlanCreate(BaseModel):
    name: str
    description: str
    price: Decimal
    currency: CurrencyType
    billing_interval: BillingInterval
    trial_period_days: int
    status: PlanStatus

class SubscriptionPlanResponse(BaseModel):
    name: str
    description: str
    price: Decimal
    currency: CurrencyType
    billing_interval: BillingInterval
    trial_period_days: int
    status: PlanStatus
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)