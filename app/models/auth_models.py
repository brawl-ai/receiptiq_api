

import datetime
from typing import Any, Dict, List, Optional, Tuple
import uuid
from fastapi import HTTPException
import jwt
from passlib.context import CryptContext
from sqlalchemy import JSON, UUID, Boolean, Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.models import Model
from app.config import logger
from app.utils import random_string


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

user_permissions_association = Table(
    'user_permissions',
    Model.metadata,
    Column('user_id', UUID(as_uuid=True), ForeignKey('users.id'), primary_key=True),
    Column('permission_id', UUID(as_uuid=True), ForeignKey('permissions.id'), primary_key=True)
)

class Permission(Model):
    __tablename__ = "permissions"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    codename: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, onupdate=datetime.datetime.now)
    
    users: Mapped[List["User"]] = relationship(
        secondary=user_permissions_association, 
        back_populates='permissions'
    )

class UserScope(Model):
    __tablename__ = "user_scopes"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    scope: Mapped[uuid.UUID] = mapped_column(String, nullable=False)
    granted_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    
    user: Mapped["User"] = relationship("User", back_populates="scopes")

class User(Model):
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    otp: Mapped[Optional[str]] = mapped_column(String(5))
    otp_expiry_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, default=datetime.datetime.now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    access_token: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, onupdate=datetime.datetime.now)
    locked_until: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), default=None)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    
    permissions: Mapped[List[Permission]] = relationship(
        secondary=user_permissions_association,
        back_populates='users'
    )
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    scopes: Mapped[List["UserScope"]] = relationship("UserScope", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        """
        Hash and set the user's password
        """
        self.password_hash = pwd_context.hash(password)
        logger.info(f"Password set for user {self.email}")

    def verify_password(self, password: str) -> bool:
        """
        Verify the user's password
        """
        if not self.password_hash:
            return False
        return pwd_context.verify(password, self.password_hash)

    async def create_otp(self, db: Session, code_length: int, code_expiry_seconds: int) -> "User":
        """
        Create the verification code for the user and set it's expiry date and time
        """
        self.otp = random_string(length=code_length)
        self.otp_expiry_at = datetime.datetime.now() + datetime.timedelta(seconds=code_expiry_seconds)
        db.add(self)
        db.commit()
        db.refresh(self)
        logger.info(f"User {self.first_name} otp {self.otp} created, expires at {self.otp_expiry_at}")
        
        return self

    async def validate_otp(self, db: Session, code: str) -> bool:
        """
        Validate the verification code and activate the user
        """
        time_now = datetime.datetime.now()
        logger.info(f"User {self.first_name} verification code {code} vs {self.otp} verification requested at {time_now} vs {self.otp_expiry_at}")
        if self.otp == code and self.otp_expiry_at > time_now:
            self.is_verified = True
            self.is_active = True
            self.otp = None
            self.otp_expiry_at = None
            db.add(self)
            db.commit()
            db.refresh(self)
            logger.info(f"User {self.first_name} verified successfully")
            return True
        else:
            logger.info(f"User {self.first_name} verification failed")
            return False
    
    async def has_perm(self, permission_codename: str) -> bool:
        """
        Check if the user has the permission
        """
        for perm in self.permissions:
            if perm.codename == permission_codename:
                return True
        return False
    
    async def has_scope(self, required_scope: str) -> bool:
        """Check if user has required scope"""
        user_scopes = [scope.scope for scope in self.scopes]
        return required_scope in user_scopes or "admin" in user_scopes
    
    def is_locked(self) -> bool:
        """Check if account is locked"""
        if self.locked_until is None:
            return False
        print(datetime.datetime.now(tz=datetime.timezone.utc), self.locked_until)
        return datetime.datetime.now(tz=datetime.timezone.utc) < self.locked_until
    
    def lock_account(self, db: Session, minutes: int = 30):
        """Lock account for specified minutes"""
        self.locked_until = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(minutes=minutes)
        self.failed_login_attempts += 1
        db.commit()


    def create_jwt_token(self, secret: str, algorithm: str, expiry_seconds: int, granted_scopes: list[str]="read") -> str:
        """
        Create a JWT token for the user, encoding the email, user_id and expiry time and return it
        """
        logger.info(f"Creating JWT token for user {self.email}")
        expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expiry_seconds)
        payload = {
            "sub": self.email,
            "user_id": str(self.id),
            "exp": expire,
            "scope": " ".join(granted_scopes)
        }
        return jwt.encode(payload=payload, key=secret, algorithm=algorithm)

    @staticmethod
    def verify_jwt_token(token: str, secret: str, algorithm: str) -> Tuple[str, str] | None:
        """
        Verify the JWT token and return the email and user_id
        """
        logger.info(f"Verifying JWT token {token}")
        try:
            payload = jwt.decode(jwt=token, key=secret, algorithms=[algorithm], options={"verify_exp": True, "verify_signature": True, "required": ["exp", "sub"]})
            return payload.get("sub", None), payload.get("user_id", None)
        except jwt.InvalidAlgorithmError:
            logger.error(f"JWT token invalid algorithm: {algorithm} on token: {token}")
            raise HTTPException(status_code=401, detail={"message": "Invalid access token"})
        except jwt.ExpiredSignatureError:
            logger.error(f"JWT expired signature on token: {token}")
            raise HTTPException(status_code=401, detail={"message": "Access Token expired"})
        except jwt.InvalidTokenError as e:
            logger.error(f"JWT invalid token: {token} error: {e}")
            raise HTTPException(status_code=401, detail={"message": "Invalid access token"})
    
    def __str__(self):
        return f"{self.first_name} - {self.email}"

class PasswordResetToken(Model):
    __tablename__ = "password_reset_tokens"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, onupdate=datetime.datetime.now)

class RefreshToken(Model):
    __tablename__ = "refresh_tokens"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, onupdate=datetime.datetime.now)

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")

class RevokedToken(Model):
    __tablename__ = "revoked_tokens"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    token_type: Mapped[str] = mapped_column(String, nullable=False)  # 'access' or 'refresh'
    revoked_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)

# Add to models.py
class LoginAttempt(Model):
    __tablename__ = "login_attempts"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(100))
    ip_address: Mapped[str] = mapped_column(String, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attempted_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now)

class AuditLog(Model):
    __tablename__ = "audit_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, unique=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    resource: Mapped[str] = mapped_column(String, nullable=True)
    ip_address: Mapped[str] = mapped_column(String, nullable=False)
    user_agent: Mapped[str] = mapped_column(String, nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)