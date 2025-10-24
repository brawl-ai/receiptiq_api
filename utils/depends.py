import base64
from datetime import datetime, timezone
import hashlib
from typing import Annotated, Any, Dict, Optional, Tuple
from sqlalchemy import create_engine, func, select
from fastapi import Depends, HTTPException, Header, Query, Request, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.orm import Session, sessionmaker
from models.subscriptions import Payment
from models.auth import RevokedToken,User
from config import get_settings, logger

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # Enable pre-ping to check connection health
    pool_size=10,        # Adjust pool size as needed
    max_overflow=20,     # Adjust overflow size as needed
    pool_recycle=3600    # Recycle connections after 1 hour
)
session_local = sessionmaker(autocommit=False,autoflush=False,bind=engine)

def get_db():
    db = None
    try:
        db = session_local()
        logger.info("Database connection established")
        yield db
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        if db:
            db.close()
        raise
    finally:
        if db:
            logger.info("Closing database connection")
            db.close()
            
async def get_app(client_id: Annotated[str, Header()], client_secret: Annotated[str, Header()]) -> Tuple[str, str]:
    if client_id == settings.client_id and client_secret == settings.client_secret:
        return (client_id, client_secret)
    else:
        raise HTTPException(status_code=401,detail={"message":"Client credentials are invalid"})
    
def is_token_revoked(token: str, db: Session) -> bool:
    """Check if token is revoked"""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    revoked_token = db.query(RevokedToken).filter(
        RevokedToken.token_hash == token_hash,
        RevokedToken.expires_at > datetime.now(tz=timezone.utc)
    ).first()
    return revoked_token is not None

async def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if is_token_revoked(token, db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload: dict = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm]
        )
        email: str = payload.get("sub")
        user_id: str = payload.get("user_id")
        scope: str = payload.get("scope")
        if email is None or user_id is None:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception
    user = db.execute(select(User).where(User.email == email,User.id == user_id)).scalars().first()
    if user is None:
        raise credentials_exception
    return user, scope

async def get_app(authorization: Annotated[str, Header(alias="Authorization")]) -> Tuple[str, str]:
    if not authorization.startswith("Basic "):
        raise HTTPException(
            status_code=401, 
            detail={"message": "Invalid authorization header format. Ensure You use `Basic x43oiru323XY` format where x43oiru323XY is base64 encoding of client_id:client_secret"}
        )
    try:
        encoded_credentials = authorization[6:]  # Remove "Basic "
        decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
        client_id, client_secret = decoded_credentials.split(':', 1)
        settings = get_settings()
        if client_id == settings.client_id and client_secret == settings.client_secret:
            return (client_id, client_secret)
        else:
            raise HTTPException(
                status_code=401,
                detail={"message": "Client credentials are invalid"},
                headers={"WWW-Authenticate": "Basic"}
            )
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=401,
            detail={"message": "Invalid authorization header encoding"},
            headers={"WWW-Authenticate": "Basic"}
        )
    
async def get_current_active_verified_user(auth_user: Tuple[User, str] = Depends(get_current_user)) -> Tuple[User, str]:
    current_user, scope = auth_user
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    if not current_user.is_verified:
        raise HTTPException(status_code=400, detail="User not verified")
    return current_user, scope

def require_scope(required_scope: str):
    def scope_checker(auth: Tuple[User, str] = Depends(get_current_active_verified_user)):
        current_user, token_scope = auth
        if not required_scope in token_scope.split(" ") and "admin" not in [sc.codename for sc in current_user.scopes]:
            print("Insufficient permission needed ",required_scope)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required scope: {required_scope}"
            )
        return current_user
    return scope_checker

def require_subscription(required_scope: str):
    def subscription_checker(scoped_user: User= Depends(require_scope(required_scope)), db: Session = Depends(get_db)):
        payment: Payment | None = db.execute(select(Payment)
                                    .where(
                                        Payment.user_id == scoped_user.id,
                                        Payment.subscription_end_at > func.now()  # Check if subscription is active
                                    )).scalar_one_or_none()
        if not payment:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"You do not have an active subscription"
            )
        return scoped_user

    return subscription_checker

async def get_query_params(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    q: Optional[str] = None,
) -> Dict[str, Any]:
    query_params = dict(request.query_params)
    query_params.pop('page', None)
    query_params.pop('size', None)
    query_params.pop('q', None)
    params = {
        "page": page,
        "size": size,
        "q": q,
        **query_params
    }
    return params