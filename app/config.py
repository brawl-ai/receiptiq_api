import logging
from honeybadger.contrib import HoneybadgerHandler
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    PROJECT_NAME: str = "ReceiptIQ API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "your-secret-key-here"  # Change in production
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 3600  # 1 hour
    VERIFICATION_CODE_LENGTH: int = 5
    VERIFICATION_CODE_EXPIRY_SECONDS: int = 300  # 5 minutes
    SMTP_HOST: str = "smtp.mailtrap.io"
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "receiptiq"
    MONGODB_USERNAME: str = ""
    MONGODB_PASSWORD: str = ""
    MONGODB_AUTH_SOURCE: str = "admin"
    HONEYBADGER_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('honeybadger')

# Configure Honeybadger
if settings.HONEYBADGER_API_KEY:
    hb_handler = HoneybadgerHandler(api_key=settings.HONEYBADGER_API_KEY)
    hb_handler.setLevel(logging.DEBUG)
    hb_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(hb_handler)