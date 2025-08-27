from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api import timedelta
from models import BillingInterval, Permission, PlanStatus,SubscriptionPlan, User, Payment, Subscription
from utils import create_paystack_subscription_plan, get_paystack_plans, get_db
from config import logger, permissions, subscription_plans, get_settings


def create_permissions(db: Session):
    for perm_name, perm_code in permissions:
        if not db.execute(
            select(Permission).where(Permission.codename == perm_code)
        ).scalar_one_or_none():
            permission = Permission(name=perm_name, codename=perm_code)
            db.add(permission)
            db.commit()

def get_first_or_none(iterable, condition):
    return next(filter(condition, iterable), None)

def create_default_admin_user(db:Session):
    settings = get_settings()
    logger.info("Adding admin user")
    admin_user = db.execute(select(User).where(User.email == settings.admin_email)).scalar_one_or_none()
    if not admin_user:
        admin_user = User()
        admin_user.first_name = "ReceiptIQ"
        admin_user.last_name = "Admin"
        admin_user.email = settings.admin_email
        admin_user.set_password(settings.admin_password)
        admin_user.is_active = True
        admin_user.is_verified = True
        permission = db.execute(select(Permission).where(Permission.codename == "admin")).scalar_one_or_none()
        admin_user.scopes.append(permission)
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
    annual_plan = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.billing_interval == BillingInterval.ANNUALLY, SubscriptionPlan.status == PlanStatus.ACTIVE)).scalar_one_or_none()
    payment_payload = {
        "event": "charge.success",
        "data": {
            "id": 0000000,
            "customer": {"email": admin_user.email},
            "plan": {"plan_code": annual_plan.plan_code},
            "amount": annual_plan.price,
            "status": "success"
        }
    }
    trump_payment = db.execute(select(Payment).where(Payment.transaction_id == payment_payload.get("data").get("id"))).scalar_one_or_none()
    if not trump_payment:
        trump_payment = Payment.create_from_paystack_response(admin_user.id, data=payment_payload.get("data"))
        db.add(trump_payment)
        db.commit()
        db.refresh(trump_payment)
    forever_subscription = db.execute(select(Subscription).where(Subscription.user_id == admin_user.id, Subscription.subscription_plan_id == annual_plan.id, Subscription.end_at > func.now())).scalar_one_or_none()
    if not forever_subscription:
        forever_subscription = Subscription()
        forever_subscription.user_id = admin_user.id
        forever_subscription.subscription_plan_id = annual_plan.id
        forever_subscription.subscription_code = "SUB0000000"
        forever_subscription.start_at = datetime.now(timezone.utc)
        forever_subscription.end_at = datetime.now(timezone.utc) + timedelta(days=730) # two years
        db.add(forever_subscription)
        db.commit()
    logger.info("Admin User ADDED")


def create_subscription_plans(db: Session):
    for (name,descr,price,currency,billing_interval,trial_period_days,status) in subscription_plans:
        
        paystack_plan = get_first_or_none(get_paystack_plans(), lambda p: p["name"] == name and not p["is_deleted"])
        if not paystack_plan:
            paystack_plan = create_paystack_subscription_plan(name=name, interval=billing_interval, amount=price, currency=currency)
        
        db_plan = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.billing_interval == BillingInterval(billing_interval), SubscriptionPlan.status == PlanStatus.ACTIVE)).scalar_one_or_none()
        if not db_plan:
            db_plan = SubscriptionPlan(
                name=name,
                description=descr,
                plan_code=paystack_plan.get("plan_code"),
                price=price,
                currency=currency,
                billing_interval=BillingInterval(billing_interval),
                trial_period_days=trial_period_days,
                status=status
            )
        else:
            db_plan.plan_code = paystack_plan.get("plan_code")
        db.add(db_plan)
        db.commit()

if __name__ == '__main__':
    try:
        db = next(get_db())
        create_permissions(db=db)
        create_subscription_plans(db=db)
        create_default_admin_user(db=db)
    except Exception as e:
        logger.error(e)
        raise e