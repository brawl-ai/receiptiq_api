import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from models import SubscriptionPlan, User, Subscription

test_user_data = {
    "first_name": "John",
    "last_name": "Doe", 
    "email": "kahenya0@gmail.com",
    "password": "SuperS3cr3t@Pass"
}

@pytest.mark.asyncio
async def test_list_subscription_plans(client, db):
    plan = SubscriptionPlan(
        name="Pro", 
        description="Pro", 
        plan_code="pro-code",
        price=1000, 
        currency="KES"
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    response = client.get("/api/v1/subscriptions/plans")
    assert response.status_code == 200
    assert any(p["name"] == "Pro" for p in response.json()["data"])

def create_user(db: Session):
    user: User = User(
        first_name=test_user_data["first_name"],
        last_name=test_user_data["last_name"],
        email=test_user_data["email"],
    )
    user.set_password(test_user_data["password"])
    user.is_active = True
    user.is_verified = True
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@patch("api.subscriptions.initiate_paystack_payment", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_start_payment_success(mock_paystack, client, db, test_settings):
    plan = SubscriptionPlan(
        name="Pro", 
        description="Pro", 
        plan_code="pro-code",
        price=1000,
        currency="KES"
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    user = create_user(db=db)
    access_token = user.create_jwt_token(test_settings.secret_key,algorithm=test_settings.algorithm,expiry_seconds=test_settings.access_token_expiry_seconds)
    mock_paystack.return_value = {"payment_url": "https://paystack.com/pay/abc123"}
    payload = {
        "plan_id": str(plan.id),
        "email": test_user_data["email"]
    }
    response = client.post(
                        url="/api/v1/subscriptions/payments/start", 
                        json=payload, 
                        cookies={"access_token":access_token}
                    )
    assert response.status_code == 200
    assert "payment_url" in response.json()
    mock_paystack.assert_awaited_once()


@patch("api.subscriptions.verify_paystack_signature", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_webhook_subscription_create(mock_verify, client, db, test_settings):
    plan = SubscriptionPlan(
        name="Pro", 
        description="Pro", 
        plan_code="pro-code",
        price=1000,
        currency="KES"
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    user = create_user(db=db)
    access_token = user.create_jwt_token(test_settings.secret_key,algorithm=test_settings.algorithm,expiry_seconds=test_settings.access_token_expiry_seconds)
    mock_verify.return_value = True
    payload = {
        "event": "subscription.create",
        "data": {
            "customer": {"email": test_user_data["email"]},
            "subscription_code": "sub_123",
            "plan": {"plan_code": "pro-code"}
        }
    }
    response = client.post(
        "/api/v1/subscriptions/payments/webhook",
        json=payload,
        headers={"x-paystack-signature": "dummy"}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Subscription Event Consumed Successfully"
    mock_verify.assert_awaited_once()



@patch("api.subscriptions.verify_paystack_signature", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_webhook_charge_success_creates_payment(mock_verify, client, db, test_settings):
    plan = SubscriptionPlan(
        name="Pro", 
        description="Pro", 
        plan_code="pro-code",
        price=1000,
        currency="KES"
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    user = create_user(db=db)
    sub = Subscription(user_id=user.id, subscription_plan_id=plan.id, subscription_code="sub_321", start_at=datetime.now(timezone.utc), end_at=datetime.now(timezone.utc) + timedelta(days=30))
    db.add(sub)
    db.commit()
    db.refresh(sub)
    access_token = user.create_jwt_token(test_settings.secret_key,algorithm=test_settings.algorithm,expiry_seconds=test_settings.access_token_expiry_seconds)
    mock_verify.return_value = True
    payload = {
        "event": "charge.success",
        "data": {
            "id": 1828382,
            "customer": {"email": user.email},
            "plan": {"plan_code": "pro-code"},
            "amount": 1500,
            "status": "success",
        }
    }
    response = client.post(
        "/api/v1/subscriptions/payments/webhook",
        json=payload,
        headers={"x-paystack-signature": "dummy"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Subscription Event Consumed Successfully"
    mock_verify.assert_awaited_once()

@patch("api.subscriptions.get_paystack_subscription_link", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_get_subscription_update_link(mock_link, client, db, test_settings):
    plan = SubscriptionPlan(
        name="Pro", 
        description="Pro", 
        plan_code="pro-code",
        price=1000,
        currency="KES"
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    user = create_user(db=db)
    sub = Subscription(user_id=user.id, subscription_plan_id=plan.id, subscription_code="sub_321", start_at=datetime.now(timezone.utc), end_at=datetime.now(timezone.utc) + timedelta(days=30))
    db.add(sub)
    db.commit()
    db.refresh(sub)
    access_token = user.create_jwt_token(test_settings.secret_key,algorithm=test_settings.algorithm,expiry_seconds=test_settings.access_token_expiry_seconds)
    mock_link.return_value = {"link": "https://paystack.com/manage/sub_test"}
    response = client.get(f"/api/v1/subscriptions/{sub.id}/update_subscription_link", cookies={"access_token":access_token})
    assert response.status_code == 200
    assert response.json()["link"].startswith("https://paystack.com")
