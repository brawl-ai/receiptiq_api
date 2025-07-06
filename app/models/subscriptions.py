from ast import Dict
import decimal
import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, DateTime, ForeignKey, Float, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column,relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.models import Model
from typing import Optional, List
from sqlalchemy import String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from enum import Enum as PyEnum

class CurrencyType(str, PyEnum):
    EUR = 'EUR'
    USD = 'USD'
    CNY = 'CNY'
    JPY = 'JPY'
    KES = 'KES'

class PlanStatus(PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"

class BillingInterval(PyEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    WEEKLY = "weekly"
    ONE_TIME = "one_time"

class PaymentStatus(PyEnum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    ABANDONED = "abandoned"
    REVERSED = "reversed"

class PaymentChannel(PyEnum):
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    USSD = "ussd"
    QR = "qr"
    MOBILE_MONEY = "mobile_money"
    BANK = "bank"

class SubscriptionPlan(Model):
    __tablename__ = "subscription_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    price: Mapped[decimal.Decimal] = mapped_column(Float(precision=10, decimal_return_scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(Enum(CurrencyType), default=CurrencyType.USD)  # ISO 4217 currency code
    billing_interval: Mapped[BillingInterval] = mapped_column(Enum(BillingInterval), default=BillingInterval.MONTHLY)
    trial_period_days: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    status: Mapped[PlanStatus] = mapped_column(Enum(PlanStatus), default=PlanStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=datetime.now)

    subscriptions: Mapped["Subscription"] = relationship("Subscription", back_populates="plan") # type: ignore


    def __repr__(self):
        return f"<SubscriptionPlan(id={self.id}, name='{self.name}', price={self.price})>"

class Payment(Model):
    __tablename__ = "payments"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=False)
    transaction_id: Mapped[Optional[int]] = mapped_column(Integer)  # Paystack ID (4099260516)
    domain: Mapped[Optional[str]] = mapped_column(String(50))  # test/live
    status: Mapped[PaymentStatus] = mapped_column(String(20), nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(255))  # Paystack reference
    receipt_number: Mapped[Optional[str]] = mapped_column(String(255))
    amount: Mapped[decimal.Decimal] = mapped_column(Float(precision=15, decimal_return_scale=2), nullable=False)  # Amount paid
    message: Mapped[Optional[str]] = mapped_column(Text)
    gateway_response: Mapped[Optional[str]] = mapped_column(String(255))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    channel: Mapped[Optional[PaymentChannel]] = mapped_column(String(50))
    currency: Mapped[str] = mapped_column(Enum(CurrencyType))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))  # Support IPv6
    payment_metadata: Mapped[Optional[str]] = mapped_column(JSONB)  # Custom metadata
    log: Mapped[Optional[str]] = mapped_column(JSONB)  # Payment log/history
    fees: Mapped[Optional[decimal.Decimal]] = mapped_column(Float(precision=15, decimal_return_scale=2))
    fees_split: Mapped[Optional[str]] = mapped_column(JSONB)  # JSON data for fee breakdown
    authorization: Mapped[Optional[Dict]] = mapped_column(JSONB)  # Full authorization object
    customer: Mapped[Optional[str]] = mapped_column(JSONB)  # Full customer object
    plan_object: Mapped[Optional[str]] = mapped_column(JSONB)  # Plan details if applicable
    split: Mapped[Optional[str]] = mapped_column(JSONB)  # Split payment details
    order_id: Mapped[Optional[str]] = mapped_column(String(255))
    requested_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Float(precision=15, decimal_return_scale=2))  # Original amount
    pos_transaction_data: Mapped[Optional[str]] = mapped_column(JSONB)  # POS specific data
    source: Mapped[Optional[str]] = mapped_column(JSONB)  # Payment source details
    fees_breakdown: Mapped[Optional[str]] = mapped_column(JSONB)  # JSON data
    connect: Mapped[Optional[str]] = mapped_column(JSONB)  # Connect details
    transaction_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    subaccount: Mapped[Optional[str]] = mapped_column(JSONB)  # Subaccount details
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=datetime.now)

    user = relationship("User", back_populates="payments")
    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="payment", foreign_keys="Subscription.payment_id")
    
    @property
    def net_amount(self) -> decimal.Decimal:
        """Calculate net amount after fees"""
        if self.fees:
            return self.amount - self.fees
        return self.amount
    
    @property
    def is_successful(self) -> bool:
        """Check if payment was successful"""
        return self.status == PaymentStatus.SUCCESS
    
    @property
    def masked_card_number(self) -> Optional[str]:
        """Return masked card number if available"""
        if self.authorization["bin"] and self.authorization["last4"]:
            return f"{self.authorization['bin']}****{self.authorization['last4']}"
        return None
    
    @classmethod
    def create_from_paystack_response(cls, user_id: uuid.UUID, subscription_id: uuid.UUID, paystack_data: dict) -> 'Payment':
        """Create Payment instance from Paystack webhook/verification response"""
        data = paystack_data.get('data', {})
        
        # Extract authorization details
        auth = data.get('authorization', {})
        customer = data.get('customer', {})
        
        return cls(
            user_id=user_id,
            subscription_id=subscription_id,
            transaction_id=data.get('id'),
            domain=data.get('domain'),
            status=PaymentStatus(data.get('status', 'pending')),
            reference=data.get('reference'),
            receipt_number=data.get('receipt_number'),
            amount=decimal.Decimal(str(data.get('amount', 0))),  # Convert from kobo to naira
            message=data.get('message'),
            gateway_response=data.get('gateway_response'),
            paid_at=datetime.fromisoformat(data.get('paid_at').replace('Z', '+00:00')) if data.get('paid_at') else None,
            created_at=datetime.fromisoformat(data.get('created_at').replace('Z', '+00:00')) if data.get('created_at') else None,
            channel=PaymentChannel(data.get('channel')) if data.get('channel') else None,
            currency=data.get('currency', 'NGN'),
            ip_address=data.get('ip_address'),
            payment_metadata=data.get('metadata'),
            log=data.get('log'),
            fees=decimal.Decimal(str(data.get('fees', 0))) / 100 if data.get('fees') else None,
            fees_split=data.get('fees_split'),
            authorization=auth,
            customer=customer,
            plan_object=data.get('plan_object'),
            split=data.get('split'),
            order_id=data.get('order_id'),
            requested_amount=decimal.Decimal(str(data.get('requested_amount', 0))) / 100 if data.get('requested_amount') else None,
            pos_transaction_data=data.get('pos_transaction_data'),
            source=data.get('source'),
            fees_breakdown=data.get('fees_breakdown'),
            connect=data.get('connect'),
            transaction_date=datetime.fromisoformat(data.get('transaction_date').replace('Z', '+00:00')) if data.get('transaction_date') else None,
            subaccount=data.get('subaccount'),
        )
    
    def __repr__(self):
        return f"<Payment(id={self.id}, reference='{self.reference}', amount={self.amount}, status='{self.status}')>"


class Subscription(Model):
    __tablename__ = "subscriptions"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payments.id"))
    subscription_plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=datetime.now)
    
    user: Mapped["User"] = relationship("User", back_populates="subscriptions") # type: ignore
    plan: Mapped["SubscriptionPlan"] = relationship("SubscriptionPlan", back_populates="subscriptions") # type: ignore
    payment: Mapped["Payment"] = relationship("Payment", back_populates="subscription", foreign_keys=[payment_id])


        
    def __str__(self):
        return f"{self.user.first_name} for: {self.plan.name} from: {self.start_at.isoformat()} to: {self.end_at.isoformat()}"