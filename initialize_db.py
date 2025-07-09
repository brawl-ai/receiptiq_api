from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BillingInterval, Permission,SubscriptionPlan
from utils import create_paystack_subscription_plan, get_paystack_plans, get_db
from config import logger, permissions, subscription_plans


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

def create_subscription_plans(db: Session):
    for (name,descr,price,currency,billing_interval,trial_period_days,status) in subscription_plans:
        
        paystack_plan = get_first_or_none(get_paystack_plans(), lambda p: p["name"] == name and not p["is_deleted"])
        if not paystack_plan:
            paystack_plan = create_paystack_subscription_plan(name=name, interval=billing_interval, amount=price, currency=currency)
        
        db_plan = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.billing_interval == BillingInterval(billing_interval))).scalar_one_or_none()
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
    except Exception as e:
        logger.error(e)
        raise e