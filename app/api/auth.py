import hashlib
import secrets
import re
from typing import Optional, Tuple, List
import datetime
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import AuditLog, LoginAttempt, PasswordResetToken, RefreshToken, RevokedToken, User
from app.schemas import ForgotPasswordRequest, ForgotPasswordResponse, RefreshTokenRequest, RefreshTokenResponse, ResetPasswordRequest, ResetPasswordResponse, RevokeTokenRequest
from app.schemas.auth import (
    UserCreate, UserResponse, TokenResponse,
    VerificationCodeRequest, VerificationCodeResponse,
    VerifyCodeRequest, LoginRequest, PasswordUpdate
)
from app.utils import generate_reset_token, hash_token, send_password_reset_email, send_verification_email
from app.depends import get_app, get_current_user, get_db, require_scope
from app.config import settings, logger
from app.rate_limiter import limiter

router = APIRouter(prefix="/auth", tags=["Auth"])

def create_refresh_token(user_id: str, db: Session) -> str:
    """Create a refresh token for a user"""
    token = secrets.token_urlsafe(settings.refresh_token_length)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=settings.refresh_token_expiry_seconds)
    refresh_token = RefreshToken(user_id=user_id,token_hash=token_hash,expires_at=expires_at)
    db.add(refresh_token)
    db.commit()
    db.refresh(refresh_token)    
    return token

def verify_refresh_token(token: str, db: Session) -> Optional[User]:
    """Verify refresh token and return user"""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    refresh_token = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked == False,
        RefreshToken.expires_at > datetime.datetime.now(tz=datetime.timezone.utc)
    ).first()
    if not refresh_token:
        return None
    return refresh_token.user

def revoke_token(token: str, token_type: str, db: Session, expires_at: datetime = None):
    """Add token to revocation list"""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if not expires_at:
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=3600) # Default 1 hr
    revoked_token = RevokedToken(
        token_hash=token_hash,
        token_type=token_type,
        expires_at=expires_at
    )
    db.add(revoked_token)
    if token_type == "refresh":
        db.query(RefreshToken).filter(
            RefreshToken.token_hash == token_hash
        ).update({"revoked": True})
    db.commit()

def revoke_all_user_tokens(user_id: str, db: Session):
    """Revoke all tokens for a user"""
    # Mark all refresh tokens as revoked
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked == False
    ).update({"revoked": True})
    
    db.commit()

def log_security_event(
    action: str,
    request: Request,
    user_id: Optional[str] = None,
    resource: Optional[str] = None,
    details: Optional[dict] = None,
    db: Session = None
):
    """Log security-related events"""
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        ip_address=get_remote_address(request),
        user_agent=request.headers.get("user-agent"),
        details=details
    )
    if db:
        db.add(audit_log)
        db.commit()
    logger.info(f"Security Event: {action}", extra={
        "user_id": user_id,
        "ip_address": get_remote_address(request),
        "resource": resource,
        "details": details
    })

class PasswordValidator:
    @staticmethod
    def validate_password(password: str) -> tuple[bool, List[str]]:
        """Validate password strength"""
        errors = []
        
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        
        if len(password) > 128:
            errors.append("Password must be less than 128 characters")
        
        if not re.search(r"[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")
        
        if not re.search(r"[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")
        
        if not re.search(r"\d", password):
            errors.append("Password must contain at least one digit")
        
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
            errors.append("Password must contain at least one special character")
        
        common_passwords = ["password", "123456", "qwerty", "admin"]
        if password.lower() in common_passwords:
            errors.append("Password is too common")
        
        return len(errors) == 0, errors

def record_login_attempt(email: str, ip_address: str, success: bool, db: Session):
    """Record login attempt"""
    attempt = LoginAttempt(
        email=email,
        ip_address=ip_address,
        success=success
    )
    db.add(attempt)
    db.commit()

def count_failed_login_attempts(email: str, db: Session, window_minutes: int = 60) -> int:
    """Count failed attempts in time window"""
    since = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(minutes=window_minutes)
    count = db.query(LoginAttempt).filter(
        LoginAttempt.email == email,
        LoginAttempt.success == False,
        LoginAttempt.attempted_at > since
    ).count()
    logger.info(f"Login attempts in last {window_minutes} mins are {count}")
    return count

@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(user_in: UserCreate, db: Session = Depends(get_db), _: Tuple = Depends(get_app)):
    """        
        Registers a new user and sends email verification OTP. Requires client 
        authentication via Basic Authorization header.
        
        **Parameters:**
        - **first_name**: User's first name
        - **last_name**: User's last name  
        - **email**: User's email address (must be unique)
        - **password**: User's password
        
        **Authentication:**
        - Client credentials via `Authorization: Basic <base64(client_id:client_secret)>`
        
        **Next Step:** Use `/otp/check` endpoint with OTP to activate account
    """
    try:
        is_valid, errors = PasswordValidator.validate_password(user_in.password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Password does not meet requirements", "errors": errors}
            )
        existing_user = db.execute(select(User).where(User.email == user_in.email)).scalars().first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with email {user_in.email} already exists"
            )
        user = User(
            first_name=user_in.first_name,
            last_name=user_in.last_name,
            email=user_in.email
        )
        user.set_password(user_in.password)
        db.add(user)
        db.commit()
        db.refresh(user)
        await user.create_otp(
            db=db,
            code_length=settings.otp_length,
            code_expiry_seconds=settings.otp_expiry_seconds
        )
        await send_verification_email(user.first_name,user.email, user.otp)
        user_data = UserResponse.model_validate(user)
        return {"message": "User created successfully. Check your email for otp code", "user": user_data.model_dump()}
    except Exception as e:
        logger.error(e)
        raise e

@router.post("/otp/get", response_model=VerificationCodeResponse)

async def get_otp(request: VerificationCodeRequest, db: Session = Depends(get_db), _: Tuple = Depends(get_app)):
    """
        Request a new OTP verification code
        
        Generates and sends a fresh OTP code to the user's email address.
        Use this to resend verification codes or get a new code if the 
        previous one expired.
        
        **Parameters:**
        - **email**: User's email address

        **Authentication:**
        - Client credentials via `Authorization: Basic <base64(client_id:client_secret)>`
        
        **Use Cases:**
        - Resend verification code during signup
        - Get new code if previous one expired
        - Replace lost or undelivered codes
        - Request one for use as the login mechanism
   """
    try:
        user: User = db.execute(select(User).where(User.email == request.email)).scalars().first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        await user.create_otp(
            db=db,
            code_length=settings.otp_length,
            code_expiry_seconds=settings.otp_expiry_seconds
        )
        await send_verification_email(user.first_name, user.email, user.otp)
        return {"message": f"OTP code sent to {user.email}"}
    except Exception as e:
        logger.error(e)
        raise e

@router.post("/otp/check")
async def check_otp(request: VerifyCodeRequest, db: Session = Depends(get_db),_: Tuple = Depends(get_app)):
    """
        Verify email with OTP code
        
        Validates the OTP code sent to user's email and returns an access token
        upon successful verification. This completes the email verification process.
        
        **Parameters:**
        - **email**: User's email address
        - **code**: OTP code received via email

        **Authentication:**
        - Client credentials via `Authorization: Basic <base64(client_id:client_secret)>`
        
        **Returns:**
        - **access_token**: JWT token for API access
        - **token_type**: "bearer"
        
        **Note:** User can immediately use the returned token to access protected endpoints
    """
    try:
        user: User = db.execute(select(User).where(User.email == request.email)).scalars().first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Missing or Deactivated User {request.email}"
            )
        is_valid = await user.validate_otp(db, request.code)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired otp code"
            )
        user_data = UserResponse.model_validate(user)
        return {"message": "User Email Verified", "user": user_data.model_dump()}
    except Exception as e:
        logger.error(e)
        raise e

@router.post("/token", response_model=TokenResponse)
@limiter.limit("5/minute")
async def token(request: Request,login_request: LoginRequest = Form(), db: Session = Depends(get_db), _ = Depends(get_app)):
    """
    OAuth2 Token Endpoint - Password Flow
    
    Exchange user credentials for an access token. Requires client authentication 
    via Basic Authorization header and user email/password in form data.
    
    **Parameters:**
    - **username**: User's email address
    - **password**: User's password
    
    **Authentication:**
    - Client credentials via `Authorization: Basic <base64(client_id:client_secret)>`
    
    **Returns:**
    - **access_token**: JWT token for API access
    - **token_type**: "Bearer"
    
    **Requirements:**
    - User must be verified and active
    - Valid client credentials required
    """
    ip_address = get_remote_address(request)
    try:        
        if login_request.grant_type != "password":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, {
                    "error": "unsupported_grant_type",
                    "error_description": f"Grant type '{login_request.grant_type}' is not supported. Use 'password'."
                })
        
        user: User = db.execute(select(User).where(User.email == login_request.username)).scalars().first()
        
        if not user or not user.verify_password(login_request.password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED,detail="Invalid Username or Password")
        
        if user.is_locked():
            raise HTTPException(status.HTTP_423_LOCKED, f"Account is locked until {user.locked_until.isoformat()}. Contact support if needed.")
        
        if not user.is_verified:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "User not verified")
        
        if not user.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Inactive user")
        
        requested_scopes = login_request.scope.split() if login_request.scope else ["read"]
        user_scopes = [scope.scope for scope in user.scopes]
        granted_scopes = [scope for scope in requested_scopes if scope in user_scopes]
        access_token = user.create_jwt_token(
            secret=settings.secret_key,
            algorithm=settings.algorithm,
            expiry_seconds=settings.access_token_expiry_seconds,
            granted_scopes=granted_scopes
        )
        refresh_token = create_refresh_token(user.id, db)
        user.failed_login_attempts = 0
        user.locked_until = None
        db.add(user)
        db.commit()
        record_login_attempt(
            email=login_request.username, 
            ip_address=ip_address, 
            success=True, 
            db=db
        )
        log_security_event(
            action="LOGIN_SUCCESS",
            request=request,
            user_id=user.id,
            details={"email": user.email, "scopes": granted_scopes},
            db=db
        )
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "refresh_token": refresh_token,
            "expires_in": settings.access_token_expiry_seconds,
            "scope": " ".join(granted_scopes)
        }
    except Exception as e:
        if user.failed_login_attempts >= 100:
            user.lock_account(db=db, minutes=30)
        record_login_attempt(login_request.username, ip_address, False, db)
        log_security_event(
            action="LOGIN_FAILED",
            request=request,
            details={"email": login_request.username, "error": str(e)},
            db=db
        )
        raise

@router.post("/token/refresh", response_model=RefreshTokenResponse)
async def refresh_token(refresh_token_request: RefreshTokenRequest,db: Session = Depends(get_db), _ = Depends(get_app)):
    """
    OAuth2 Token Refresh Endpoint
    
    Exchange a valid refresh token for a new access token and optionally 
    a new refresh token.
    
    **Parameters:**
    - **refresh_token**: Valid refresh token
    - **grant_type**: Must be "refresh_token"
    
    **Authentication:**
    - Client credentials via `Authorization: Basic <base64(client_id:client_secret)>`
    
    **Returns:**
    - **access_token**: New JWT access token
    - **token_type**: "Bearer"
    - **refresh_token**: New refresh token (optional)
    - **expires_in**: Access token expiration in seconds
    """
    if refresh_token_request.grant_type != "refresh_token":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "unsupported_grant_type", "error_description": "Only 'refresh_token' grant type is supported"}
        )
    user: User = verify_refresh_token(refresh_token_request.refresh_token, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_grant", "error_description": "Invalid or expired refresh token"}
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_grant", "error_description": "User account is inactive"}
        )
    access_token = user.create_jwt_token(
        secret=settings.secret_key,
        algorithm=settings.algorithm,
        expiry_seconds=settings.access_token_expiry_seconds
    )
    new_refresh_token = create_refresh_token(user.id, db)
    revoke_token(refresh_token_request.refresh_token, "refresh", db)
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "refresh_token": new_refresh_token,
        "expires_in": settings.access_token_expiry_seconds
    }

@router.post("/token/revoke")
async def revoke_token_endpoint(revoke_token_request: RevokeTokenRequest,db: Session = Depends(get_db),_ = Depends(get_app)):
    """
    OAuth2 Token Revocation Endpoint
    
    Revoke an access token or refresh token, making it immediately invalid.
    
    **Parameters:**
    - **token**: Token to revoke (access or refresh token)
    - **token_type_hint**: Optional hint ("access_token" or "refresh_token")
    
    **Authentication:**
    - Client credentials via `Authorization: Basic <base64(client_id:client_secret)>`
    
    **Note:** Always returns 200 OK regardless of token validity for security
    """
    try:
        if revoke_token_request.token_type_hint == "refresh_token":
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            refresh_token_obj = db.query(RefreshToken).filter(
                RefreshToken.token_hash == token_hash
            ).first()
            if refresh_token_obj:
                revoke_token(token, "refresh", db, refresh_token_obj.expires_at)
            else:
                revoke_token(token, "access", db)
        else:
            revoke_token(token, "access", db)
            
    except Exception as e:
        logger.error(f"Error revoking token: {str(e)}")
    return {"message": "Token revocation successful"}

@router.post("/password/forgot")
@limiter.limit("3/hour")
async def forgot_password(request: Request, forgot_password_request: ForgotPasswordRequest, db: Session = Depends(get_db), _: Tuple = Depends(get_app)):
    """
        Request password reset link

        **Authentication:**
        - Client credentials via `Authorization: Basic <base64(client_id:client_secret)>`
        
        Sends a password reset token to the user's email if the account exists.
        Always returns success message for security (doesn't reveal if email exists).
    """
    user: User = db.execute(select(User).where(User.email == forgot_password_request.email)).scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User {forgot_password_request.email} not found"
        )
    token = generate_reset_token(settings.password_reset_token_length)
    expires_at = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(seconds=settings.password_reset_token_expiry_seconds)
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False
    ).update({"used": True})
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=expires_at
    )
    db.add(reset_token)
    db.commit()
    await send_password_reset_email(user.email, token)
    return ForgotPasswordResponse(message="If an account with that email exists, you will receive a password reset link shortly.")

@router.post("/password/reset")
async def reset_password(reset_password_request: ResetPasswordRequest, db: Session = Depends(get_db), _: Tuple = Depends(get_app)):
    """
    Reset password with token
    
    Uses the reset token from email to set a new password. Token must be 
    valid and not expired.
    
    **Parameters:**
    - **email**: User's email address
    - **token**: Reset token from email
    - **new_password**: New password to set

    **Authentication:**
        - Client credentials via `Authorization: Basic <base64(client_id:client_secret)>`
    """
    token_hash = hash_token(reset_password_request.token)
    user: User = db.execute(select(User).where(User.email == reset_password_request.email)).scalars().first()
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False,
        PasswordResetToken.expires_at > datetime.datetime.now(tz=datetime.timezone.utc)
    ).first()
    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or Expired Reset Token"
        )
    user.set_password(reset_password_request.new_password)
    db.add(user)    
    db.query(PasswordResetToken).filter(
        PasswordResetToken.id == reset_token
    ).update({"used": True})
    db.commit()
    db.refresh(user)
    return ResetPasswordResponse(
            message="Password has been reset successfully. Please log in with your new password."
        )

@router.post("/password/change", response_model=UserResponse)
async def change_password(
    request: Request,
    password_update: PasswordUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
        Change current password
        
        Updates the logged-in user's password. Requires current password for verification.
        
        **Parameters:**
        - **current_password**: User's current password
        - **new_password**: New password to set
    """
    is_valid, errors = PasswordValidator.validate_password(password_update.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "New password does not meet requirements", "errors": errors}
        )
    if not current_user.verify_password(password_update.current_password):
        log_security_event(
            action="PASSWORD_CHANGE_FAILED",
            request=request,
            user_id=current_user.id,
            details={"reason": "incorrect_current_password"},
            db=db
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect current password"
        )
    current_user.set_password(password_update.new_password)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    revoke_all_user_tokens(current_user.id, db)
    log_security_event(
        action="PASSWORD_CHANGED",
        request=request,
        user_id=current_user.id,
        details={"tokens_revoked": True},
        db=db
    )
    return UserResponse.model_validate(current_user)

@router.get("/me", response_model=UserResponse)
async def get_user_profile(current_user: User = Depends(require_scope("read:profile")),):
    """
    Get current user profile
    Returns the authenticated user's profile information.
    """
    return current_user

@router.post("/logout")
async def logout(
    request: Request,
    token: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    User Logout
    
    Logout the current user by revoking their access token and all refresh tokens.
    
    **Parameters:**
    - **token**: Current access token
    
    **Authentication:**
    - Valid access token (Bearer token)
    
    **Process:**
    1. Revokes the current access token
    2. Revokes all refresh tokens for the user
    3. User must re-authenticate to get new tokens
    """
    try:
        revoke_token(token, "access", db)
        revoke_all_user_tokens(current_user.id, db)
        log_security_event(
            action="LOGOUT",
            request=request,
            user_id=current_user.id,
            db=db
        )
        logger.info(f"User {current_user.id} logged out successfully")
        return {"message": "Logout successful"}
    except Exception as e:
        logger.error(f"Error during logout for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "An error occurred during logout"}
        )