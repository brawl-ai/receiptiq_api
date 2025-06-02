from fastapi import APIRouter, Depends, HTTPException, status
from app.models.auth import User
from app.schemas.auth import (
    UserCreate, UserResponse, TokenResponse,
    VerificationCodeRequest, VerificationCodeResponse,
    VerifyCodeRequest, LoginRequest
)
from app.utils import send_verification_email
from app.depends import get_current_user
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserResponse)
async def register(user_in: UserCreate):
    """
    Register a new user
    """
    # Check if user already exists
    if User.objects(email=user_in.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create new user
    user = User(
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        email=user_in.email
    )
    user.save()

    # Create and send verification code
    await user.create_verification_code(
        code_length=settings.VERIFICATION_CODE_LENGTH,
        code_expiry_seconds=settings.VERIFICATION_CODE_EXPIRY_SECONDS
    )
    await send_verification_email(user.email, user.verification_code)

    return user

@router.post("/verify-code", response_model=VerificationCodeResponse)
async def request_verification_code(request: VerificationCodeRequest):
    """
    Request a new verification code
    """
    user: User = User.objects(email=request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already verified"
        )

    await user.create_verification_code(
        code_length=settings.VERIFICATION_CODE_LENGTH,
        code_expiry_seconds=settings.VERIFICATION_CODE_EXPIRY_SECONDS
    )
    await send_verification_email(user.email, user.verification_code)

    return {"message": "Verification code sent successfully"}

@router.post("/verify", response_model=TokenResponse)
async def verify_code(request: VerifyCodeRequest):
    """
    Verify user's email with the verification code
    """
    user: User = User.objects(email=request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    is_valid = await user.validate_verification_code(request.code)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code"
        )

    # Create access token
    access_token = user.create_jwt_token(
        secret=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        expiry_seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post("/login", response_model=VerificationCodeResponse)
async def request_login_otp(request: LoginRequest):
    """
    Request OTP for login
    """
    user = User.objects(email=request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not verified"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    # Create and send OTP
    await user.create_verification_code(
        code_length=settings.VERIFICATION_CODE_LENGTH,
        code_expiry_seconds=settings.VERIFICATION_CODE_EXPIRY_SECONDS
    )
    await send_verification_email(user.email, user.verification_code)

    return {"message": "Login OTP sent successfully"}

@router.post("/token", response_model=TokenResponse)
async def login_with_otp(request: VerifyCodeRequest):
    """
    Login with email and OTP to get access token
    """
    user = User.objects(email=request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not verified"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    # Validate OTP
    is_valid = await user.validate_verification_code(request.code)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP"
        )
    
    access_token = user.create_jwt_token(
        secret=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        expiry_seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Get current user information
    """
    return current_user 