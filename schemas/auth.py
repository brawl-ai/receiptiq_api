from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import Form
from pydantic import BaseModel, EmailStr, Field, ConfigDict, constr

class LoginRequest(BaseModel):
    username: EmailStr = Field(..., example="user@example.com", description="User's email address")
    password: str = Field(..., example="supersecret", description="User's password")
    scope: Optional[str] = "read:profile"
    grant_type: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., example="user@example.com", description="User's email address")

class ForgotPasswordResponse(BaseModel):
    message: str

class ResetPasswordRequest(BaseModel):
    email: str
    token: str
    new_password: str

class ResetPasswordResponse(BaseModel):
    message: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str = Form(...)
    grant_type: str = Form(..., regex="^refresh_token$")

class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None

class RevokeTokenRequest(BaseModel):
    token: str = Form(...)
    token_type_hint: Optional[str] = Form(None, regex="^(access_token|refresh_token)$")

class LogoutRequest(BaseModel):
    token: str = Form(...)

class PermissionResponse(BaseModel):
    id: UUID
    name: str = Field(..., min_length=1, max_length=100)
    codename: str = Field(..., min_length=1, max_length=100)
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=100)

class UserUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None

class UserResponse(UserBase):
    id: UUID
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    scopes: List[PermissionResponse] = []

    model_config = ConfigDict(from_attributes=True)

class UserWithToken(UserResponse):
    access_token: str

class VerificationCodeRequest(BaseModel):
    email: EmailStr

class VerificationCodeResponse(BaseModel):
    message: str = "Verification code sent successfully"

class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=5, max_length=5)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None

class TokenData(BaseModel):
    email: str
    user_id: UUID

class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)

