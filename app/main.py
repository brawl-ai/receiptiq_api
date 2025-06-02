from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, files, projects
from app.database import connect_to_mongodb, close_mongodb_connection
from app.config import settings
import logging

logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Startup")
    connect_to_mongodb()
    yield
    close_mongodb_connection()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Modify this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(projects.router, prefix=settings.API_V1_STR)
app.include_router(files.router, prefix="/files")

@app.get(f"{settings.API_V1_STR}")
async def root():
    """
    Root endpoint
    """
    return {
        "message": "Welcome to ReceiptIQ API",
        "version": settings.VERSION
    } 