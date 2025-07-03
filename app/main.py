from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select

from .models import Permission, Model
from .api import auth, projects, fields, files
from .depends import engine, session_local
from .config import settings, logger, permissions
from .rate_limiter import limiter
from contextlib import asynccontextmanager

def init_db():
    """
    Initialize database tables
    """
    try:
        Model.metadata.create_all(bind=engine)
        db = session_local()
        for (perm_name, perm_code) in permissions:
            if not db.execute(select(Permission).where(Permission.codename == perm_code)).scalar_one_or_none():
                permission = Permission(name=perm_name,codename=perm_code)
                db.add(permission)
                db.commit()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {str(e)}")
        raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    openapi_url=f"{settings.api_v1_str}/openapi.json",
    lifespan=lifespan
)
app.state.limiter = limiter
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(auth.router, prefix=settings.api_v1_str)
app.include_router(projects.router, prefix=settings.api_v1_str)
app.include_router(fields.router, prefix=settings.api_v1_str)
app.include_router(files.router, prefix="/files")

@app.get(f"{settings.api_v1_str}")
async def root():
    """
    Root endpoint
    """
    return {
        "message": "Welcome to ReceiptIQ API",
        "version": settings.api_v1_str
    } 