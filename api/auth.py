import hashlib
import secrets
from typing import Tuple
import datetime
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session
from models import LoginAttempt, PasswordResetToken, Permission, RefreshToken, RevokedToken, User
from schemas import ForgotPasswordRequest, ForgotPasswordResponse, RefreshTokenResponse, ResetPasswordRequest, ResetPasswordResponse, RevokeTokenRequest, UserUpdate
from schemas.auth import (
    GoogleCallback, UserCreate, UserResponse, TokenResponse,
    VerificationCodeRequest, VerificationCodeResponse,
    VerifyCodeRequest, LoginRequest, PasswordUpdate
)
from utils import PasswordValidator, generate_reset_token, hash_token, get_app, get_current_user, get_db, require_scope, limiter, get_google_access_token, get_google_userinfo
from celery_app import send_password_reset_email, send_verification_email
from config import get_settings, logger

settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Auth"])

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
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked == False
    ).update({"revoked": True})
    
    db.commit()

def record_login_attempt(http_request: Request, email: str, success: bool, db: Session):
    """Record login attempt"""
    attempt = LoginAttempt(
        email=email,
        ip_address= get_remote_address(http_request),
        success=success
    )
    db.add(attempt)
    db.commit()

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
        - **accepted_terms**: Whether the user has accepted terms & conditions
        
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
            email=user_in.email,
            accepted_terms=user_in.accepted_terms
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
        send_verification_email.delay(user.first_name,user.email, user.otp)
        user_data = UserResponse.model_validate(user)
        return {"message": "User created successfully. Check your email for otp code", "user": user_data.model_dump()}
    except Exception as e:
        logger.error(e)
        raise e

@router.post("/otp/get", response_model=VerificationCodeResponse)
@limiter.limit("5/minute")
async def get_otp(request: Request,get_code_request: VerificationCodeRequest, db: Session = Depends(get_db), _: Tuple = Depends(get_app)):
    """
        Request a new OTP verification code
        
        Generates and sends a fresh OTP code to the user's email address.
        Use this to resend verification codes or get a new code if the previous one expired.
        
        **Parameters:**
        - **email**: User's email address

        **Authentication:**
        - Client credentials via `Authorization: Basic <base64(client_id:client_secret)>`
   """
    try:
        user: User | None = db.execute(select(User).where(User.email == get_code_request.email)).scalars().first()
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
        send_verification_email.delay(user.first_name, user.email, user.otp)
        return {"message": f"OTP code sent to {user.email}"}
    except Exception as e:
        logger.error(e)
        raise e

@router.post("/otp/check")
@limiter.limit("5/minute")
async def check_otp(request: Request, verify_request: VerifyCodeRequest, db: Session = Depends(get_db),_: Tuple = Depends(get_app)):
    """
        Verify email with OTP code
        
        Validates the OTP code sent to user's email and returns an access token upon successful verification. 
        This completes the email verification process.
        
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
        user: User | None = db.execute(select(User).where(User.email == verify_request.email)).scalars().first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Missing or Deactivated User {verify_request.email}"
            )
        is_valid = await user.validate_otp(db, verify_request.code)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired otp code"
            )
        for perm in db.execute(select(Permission).where(Permission.codename != "admin")).scalars():
            if perm not in user.scopes:
                user.scopes.append(perm)
                db.add(user)
                db.commit()
                db.refresh(user)
        user_data = UserResponse.model_validate(user)
        return {"message": "User Email Verified", "user": user_data.model_dump()}
    except Exception as e:
        logger.error(e)
        raise e

@router.post("/token", response_model=TokenResponse)
@limiter.limit("10/minute")
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
    user = None
    try:        
        if login_request.grant_type != "password":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, 
                {
                    "error": "unsupported_grant_type",
                    "error_description": f"Grant type '{login_request.grant_type}' is not supported. Use 'password'."
                }
            )
        
        user: User = db.execute(select(User).where(User.email == login_request.username)).scalars().first()
        
        if not user or not user.verify_password(login_request.password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED,detail="Invalid Username or Password")
        
        if user.is_locked:
            raise HTTPException(status.HTTP_423_LOCKED, f"Account is locked until {user.locked_until.isoformat()}. Contact support if needed.")
        
        if not user.is_verified:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "User not verified")
        
        if not user.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Inactive user")
        
        requested_scopes = login_request.scope.split() if login_request.scope else ["read:profile"]
        user_scopes = [scope.codename for scope in user.scopes]
        granted_scopes = [scope for scope in requested_scopes if scope in user_scopes]
        access_token_age_seconds = settings.access_token_expiry_seconds if login_request.is_remember_me else 3600 # token is valid for 1hr if you don't ask to be remembered
        access_token = user.create_jwt_token(
            secret=settings.secret_key,
            algorithm=settings.algorithm,
            expiry_seconds=access_token_age_seconds,
            granted_scopes=granted_scopes
        )
        refresh_token_age_seconds = 60*60*24*30 if login_request.is_remember_me else 3600 # token is valid for 1hr if you don't ask to be remembered
        refresh_token = user.create_refresh_token(db)
        user.failed_login_attempts = 0
        user.locked_until = None
        db.add(user)
        db.commit()
        record_login_attempt(
            http_request=request,
            email=login_request.username, 
            success=True, 
            db=db
        )
        response = JSONResponse(content={
            "success": True
        })
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=access_token_age_seconds,
            path="/",
            domain=".receiptiq.co" if settings.environment == "production" else None
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=refresh_token_age_seconds,
            path="/",
            domain=".receiptiq.co" if settings.environment == "production" else None
        )
        return response

    except Exception as e:
        if user:
            if user.failed_login_attempts >= 10:
                user.lock_account(db=db, minutes=5)
            else:
                user.failed_login_attempts += 1
            db.commit()
        record_login_attempt(
            http_request=request,
            email=login_request.username,
            success=False,
            db=db
        )
        if isinstance(e, HTTPException):
            raise e
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"message":f"{e}"})

@router.post("/token/refresh", response_model=RefreshTokenResponse)
async def refresh_token(request: Request,db: Session = Depends(get_db), _ = Depends(get_app)):
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
    - **success**: True/False
    """
    try:
        _refresh_token = request.cookies.get("refresh_token")
        if not _refresh_token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
        user: User | None = User.verify_refresh_token(_refresh_token, db)
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
            expiry_seconds=settings.access_token_expiry_seconds,
            granted_scopes=[perm.codename for perm in user.scopes]
        )
        new_refresh_token = user.create_refresh_token(db)
        revoke_token(_refresh_token, "refresh", db)
        response = JSONResponse(content={"success": True})
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=settings.access_token_expiry_seconds,
            path="/",
            domain=".receiptiq.co" if settings.environment == "production" else None
        )
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=settings.refresh_token_expiry_seconds,
            path="/",
            domain=".receiptiq.co" if settings.environment == "production" else None
        )
        return response
    except Exception as e:
        logger.error(e)
        if isinstance(e, HTTPException):
            raise e
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"message":f"{e}"})

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

    **Useful for** OAuth2 spec so other apps can revoke a user’s token, not just the user themselves.:
    - Mobile apps
    - Integrations
    - Admin or security systems
    """
    try:
        if revoke_token_request.token_type_hint == "refresh_token":
            token_hash = hashlib.sha256(revoke_token_request.token.encode()).hexdigest()
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
    user: User | None = db.execute(select(User).where(User.email == forgot_password_request.email)).scalars().first()
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
    send_password_reset_email.delay(user.email, token)
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
        PasswordResetToken.id == reset_token.id
    ).update({"used": True})
    db.commit()
    db.refresh(user)
    return ResetPasswordResponse(
            message="Password has been reset successfully. Please log in with your new password."
        )

@router.post("/password/change", response_model=ResetPasswordResponse)
async def change_password(request: Request, password_update: PasswordUpdate, current_user: User = Depends(require_scope("write:profile")), db: Session = Depends(get_db)):
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect current password"
        )
    current_user.set_password(password_update.new_password)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    revoke_all_user_tokens(current_user.id, db)
    return ResetPasswordResponse(
            message="Password has been updated successfully."
        )

@router.get("/me", response_model=UserResponse)
async def get_user_profile(current_user: User = Depends(require_scope("read:profile")),):
    """
    Get current user profile
    Returns the authenticated user's profile information.
    """
    return current_user

@router.patch("/me", status_code=status.HTTP_200_OK)
async def update_user_profile(update_payload: UserUpdate,current_user: User = Depends(require_scope("write:profile")),db: Session = Depends(get_db)):
    """
    Update current user profile
    """
    current_user.first_name = update_payload.first_name if update_payload.first_name else current_user.first_name
    current_user.last_name = update_payload.last_name if update_payload.last_name else current_user.last_name
    current_user.is_active = update_payload.is_active if update_payload.is_active else current_user.is_active
    if update_payload.email:
        current_user.email = update_payload.email
        current_user.is_verified = False
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    if not current_user.is_verified:
        await current_user.create_otp(
            db=db,
            code_length=settings.otp_length,
            code_expiry_seconds=settings.otp_expiry_seconds
        )
        send_verification_email.delay(current_user.first_name,current_user.email, current_user.otp)
    user_data = UserResponse.model_validate(current_user)
    return {"message": "User updated successfully. Any new email needs to be verified", "user": user_data.model_dump()}

@router.post("/logout")
async def logout(request: Request, auth: Tuple[User, str] = Depends(get_current_user), db: Session = Depends(get_db)):
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
    current_user, scope = auth
    token = request.cookies.get("access_token")
    try:
        revoke_token(token, "access", db)
        revoke_all_user_tokens(current_user.id, db)
        logger.info(f"User {current_user.id} logged out successfully")
        response = JSONResponse(content={"message": "Logout successful"})
        response.delete_cookie(
            key="access_token",
            path="/",
            domain=".receiptiq.co" if settings.environment == "production" else None,
            secure=True,
            httponly=True,
            samesite="lax"
        )
        response.delete_cookie(
            key="refresh_token",
            path="/",
            domain=".receiptiq.co" if settings.environment == "production" else None,
            secure=True,
            httponly=True,
            samesite="strict"
        )
        return response
    except Exception as e:
        logger.error(f"Error during logout for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "An error occurred during logout"}
        )

@router.get("/google/login")
async def google_login(request: Request, _ = Depends(get_app)):
    try:
        google_auth_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
        scope = "openid email profile"
        redirect_url = (
            f"{google_auth_endpoint}"
            f"?response_type=code"
            f"&client_id={settings.google_client_id}"
            f"&redirect_uri={settings.google_redirect_uri}"
            f"&scope={scope}"
            f"&access_type=offline"
            f"&prompt=consent"
        )
        return JSONResponse(status_code=status.HTTP_200_OK, content={"redirect_to": redirect_url})
    except Exception as e:
        raise e

@router.post("/google/callback")
async def google_callback(request: Request, google_callback_data: GoogleCallback, db: Session = Depends(get_db), _ = Depends(get_app)):
    # Exchange authorization code for google access token
    google_access_code = await get_google_access_token(code=google_callback_data.code)
    # fetch google user email
    user_info = await get_google_userinfo(access_token=google_access_code)
    # get or create user
    email = user_info.get("email")
    first_name = user_info.get("given_name") or user_info.get("name")
    last_name = user_info.get("family_name") or user_info.get("name")
    user: User | None = db.execute(select(User).where(User.email == email)).scalars().first()
    normal_user_permissions = db.execute(select(Permission).where(Permission.codename != "admin")).scalars()
    if not user:
        user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            is_active=True,
            is_verified=True,
        )
        user.set_password(secrets.token_urlsafe(10))
        for perm in normal_user_permissions:
            if perm not in user.scopes:
                user.scopes.append(perm)
        db.add(user)
        db.commit()
        db.refresh(user)
        print(user.scopes)
    record_login_attempt(
        http_request=request,
        email=email, 
        success=True, 
        db=db
    )
    user_scopes = [scope.codename for scope in user.scopes]
    access_token = user.create_jwt_token(
        secret=settings.secret_key,
        algorithm=settings.algorithm,
        expiry_seconds=settings.access_token_expiry_seconds,
        granted_scopes=user_scopes
    )
    response = JSONResponse(content={"success": True})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.access_token_expiry_seconds,
        path="/",
        domain=".receiptiq.co" if settings.environment == "production" else None
    )
    refresh_token_age_seconds = 60*60*24*30 if google_callback_data.remember_me else 3600 # token is valid for 1hr if you don't ask to be remembered
    refresh_token = user.create_refresh_token(db)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=refresh_token_age_seconds,
        path="/",
        domain=".receiptiq.co" if settings.environment == "production" else None
    )
    return response
    