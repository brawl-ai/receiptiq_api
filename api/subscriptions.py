from datetime import datetime, timedelta, timezone
import json
from uuid import UUID
from typing import Any, Dict, Tuple
from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api import ListResponse
from models import Payment, SubscriptionPlan, User
from schemas import StartPaymentPayload,SubscriptionPlanResponse
from schemas.subscriptions import PaymentResponse
from utils import get_paystack_subscription_link, paginate, get_obj_or_404, get_current_active_verified_user, get_db, get_query_params, verify_paystack_payment, verify_paystack_signature, initiate_paystack_payment
from config import logger


router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.get("/plans", response_model=ListResponse)
async def list_plans(
    params: Dict[str, Any] = Depends(get_query_params),
    db: Session = Depends(get_db),
):
    """
    List subscription plans
    """
    params["status"]="ACTIVE"
    return await paginate(
        db=db, model=SubscriptionPlan, schema=SubscriptionPlanResponse, **params
    )


@router.post("/payments/start", response_model=Dict)
async def start_payment(
    start_payment_request: StartPaymentPayload,
    auth: Tuple[User, str] = Depends(get_current_active_verified_user),
    db: Session = Depends(get_db),
):
    """
    Initiate Payment for a given subscription
    """
    user, _ = auth
    plan: SubscriptionPlan = await get_obj_or_404(
        db=db, model=SubscriptionPlan, id=start_payment_request.plan_id
    )
    if not plan.plan_code:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail = f"Plan {plan} has no plan code. Please sync with payment gateway and update this plan"
        )
    payment: Payment | None = db.execute(select(Payment).where(
            Payment.subscription_plan_id == plan.id,
            Payment.user_id == user.id,
            Payment.subscription_end_at > func.now()  # Check if subscription is active
        )).scalar_one_or_none()
    if payment:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail = f"You are already subscribed to {plan} ending {payment.subscription_end_at.isoformat()}"
        )
    paystack_response = await initiate_paystack_payment(
        email=user.email,
        amount=plan.price,
        currency=plan.currency.value,
        plan=plan.plan_code
    )
    return paystack_response


@router.post("/payments/webhook", response_model=Dict, status_code=status.HTTP_200_OK)
async def complete_payment(request: Request, db: Session = Depends(get_db)):
    """
        Webhook called with payment payload
    """
    await verify_paystack_signature(request=request)
    
    body = await request.body()
    payload = json.loads(body.decode("utf-8"))
    logger.debug(f"/payments/webhook decoded payload: {payload}")
    event = payload.get("event")
    data = payload.get("data")

    email = data["customer"]["email"]
    user: User | None = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user:
        logger.error(f"Customer with email {email} was not found on the system")
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail = f"Customer with email {email} was not found on the system"
        )
    
    match event:
        
        case "subscription.create":
            """
                A subscription was created for the customer who was charged.
                Get the subscription_code and plan_code
            """ 
            plan_code = data["plan"]["plan_code"]
            plan: SubscriptionPlan | None = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.plan_code == plan_code)).scalar_one_or_none()
            if not plan:
                logger.error(f"SubscriptionPlan with plan_code {plan_code} was not found on the system")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=f"SubscriptionPlan with plan_code {plan_code} was not found on the system")

        case "charge.success":
            """
                The transaction was successful. 
                Add a payment to db
            """
            plan_code = data["plan"]["plan_code"]
            if not plan_code:
                return {"message": "No plan txn accepted"}
            plan: SubscriptionPlan | None = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.plan_code == plan_code)).scalar_one_or_none()
            if not plan:
                logger.error(f"SubscriptionPlan with plan_code {plan_code} was not found on the system")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=f"SubscriptionPlan with plan_code {plan_code} was not found on the system")

            payment: Payment | None = db.execute(select(Payment).where(Payment.transaction_id == data["id"])).scalar_one_or_none()
            if not payment:
                data["subscription_plan_id"] = plan.id
                data["subscription_start_at"] = datetime.now(timezone.utc)
                data["subscription_end_at"] = datetime.now(timezone.utc) + timedelta(days=plan.days)
                payment = Payment.create_from_paystack_response(user_id=user.id, data=data)
                db.add(payment)
                db.commit()
                db.refresh(payment)

        case "invoice.create":
            """ 
                Indicates a charge attempt will be made on the subscription. sent 3 days before the next payment date.
                TODO: Email the user reminder of upcoming payment
            """
            logger.info(f"User: {user.email} upcoming payment for subscription {data['subscription']['subscription_code']} via invoice: {data['invoice_code']} on: {data['paid_at']}")

        case "invoice.payment_failed":
            """
                It's the next payment date but charge attempt failed.
                TODO: Email alert to user
            """
            logger.warning(f"User: {user.email} payment failed for invoice: {data['invoice_code']} status: {data['status']}")


        case "invoice.update":
            """
                Sent after the charge attempt and will contain the final status of the invoice for this subscription payment, as well as information on the charge if it was successful
                TODO: Email user of final status
            """
            logger.info(f"User: {user.email} invoice: {data['invoice_code']} final status: {data['status']} transaction: {data['transaction']}")


        case "subscription.not_renew":
            """
                Indicates that the subscription will not renew on the next payment date. user has cancelled so their benefits should expire at the next payment date.
                TODO: Email user of the end date of benefits
            """
            logger.warning(f"User: {user.email} cancelled subscription: {data['subscription_code']}")


        case "subscription.disable":
            """
                On the next payment date, a subscription.disable event will be sent to indicate that the subscription has been cancelled.
                TODO: Email user that benefits are now terminated
            """
            logger.warning(f"User: {user.email} cancelled subscription: {data['subscription_code']} completed")
        
        case _:
            raise HTTPException(
                detail={"message": f"Unexpected Subscription Event: {event}"},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    
    return {"message": "Subscription Event Consumed Successfully"}

@router.get("/")
async def get_subscriptions(
    params: Dict[str, Any] = Depends(get_query_params),
    auth: Tuple[User, str] = Depends(get_current_active_verified_user),
    db: Session = Depends(get_db)
):
    user, scope = auth
    params["user_id"] = user.id
    return await paginate(
        db=db,
        model=Payment,
        schema=PaymentResponse,
        **params
    )

@router.get("/payments/check/{reference}")
async def check_payment(
    reference: str,
    auth: Tuple[User, str] = Depends(get_current_active_verified_user),
    db: Session = Depends(get_db)
):
    user, scope = auth
    payment_object: dict = await verify_paystack_payment(reference)
    return payment_object

@router.get("/{subscription_id}/update_subscription_link")
async def get_manage_subscriptions_link(
    subscription_id: UUID,
    auth: Tuple[User, str] = Depends(get_current_active_verified_user),
    db: Session = Depends(get_db)
):
    subscription: Payment = await get_obj_or_404(db=db, model=Payment, id=subscription_id)
    paystack_link_response = await get_paystack_subscription_link(subscription.subscription_code)
    return paystack_link_response