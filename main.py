from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from honeybadger import honeybadger
from honeybadger.contrib.fastapi import HoneybadgerRoute
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api import auth, projects, fields, files, receipts, data, subscriptions
from config import settings, logger
from utils import limiter

honeybadger.configure(environment=settings.environment, api_key=settings.honeybadger_api_key,force_report_data=True)
app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    openapi_url=f"{settings.api_v1_str}/openapi.json"
)
app.router.route_class = HoneybadgerRoute
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
app.include_router(receipts.router, prefix=settings.api_v1_str)
app.include_router(data.router, prefix=settings.api_v1_str)
app.include_router(subscriptions.router, prefix=settings.api_v1_str)
app.include_router(files.router, prefix="/files")

@app.get(f"{settings.api_v1_str}")
async def root():
    """
    Root endpoint
    """
    logger.warning(f"Accessing root of the app")
    # x = 23/0
    return {
        "message": "Welcome to ReceiptIQ API",
        "version": settings.api_v1_str
    } 