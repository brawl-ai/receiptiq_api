import logging
from honeybadger.contrib import HoneybadgerHandler
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    project_name: str = "ReceiptIQ API"
    version: str = "0.0.1"
    api_v1_str: str = "/api/v1"
    secret_key: str
    algorithm: str = "HS256"
    access_token_expiry_seconds: int = 3600  # 1 hour
    otp_length: int 
    otp_expiry_seconds: int  = 300  # 5 minutes
    password_reset_token_length: int = 32
    password_reset_token_expiry_seconds: int = 300
    refresh_token_length: int = 128
    refresh_token_expiry_seconds: int = 2592000 # 30 days
    frontend_url: str = ""
    postgres_user: str 
    postgres_password: str 
    postgres_db: str 
    postgres_host: str 
    postgres_port: str
    honeybadger_api_key: str = None
    openai_api_key: str = None
    client_id: str = None
    client_secret: str = None
    resend_api_key: str
    email_from: str
    email_reply_to: str

    
    @property
    def database_url(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

settings = Settings()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('honeybadger')

# Configure Honeybadger
if settings.honeybadger_api_key:
    hb_handler = HoneybadgerHandler(api_key=settings.honeybadger_api_key)
    hb_handler.setLevel(logging.DEBUG)
    hb_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(hb_handler)

permissions = [
    ('Admin','admin'),
    ('Read Profile','read:profile'),
    ('Update Profile and Password','write:profile'),
    ('Read Projects','read:projects'),
    ('Create/Update Projects','write:projects')
]