import logging
from honeybadger import Honeybadger, contrib
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    environment: str = "development"
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
    paystack_secret_key: str
    paystack_base_url: str
    aws_access_key_id: str
    aws_endpoint_url_s3: str
    aws_region: str
    aws_secret_access_key: str
    bucket_name: str
    
    @property
    def database_url(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

settings = Settings()

logger = logging.getLogger('HB')
hb = Honeybadger()
hb.configure(environment=settings.environment, api_key=settings.honeybadger_api_key,force_report_data=True)
hb_handler = contrib.HoneybadgerHandler(api_key=settings.honeybadger_api_key)
hb_handler.honeybadger = hb
hb_handler.setLevel(logging.INFO)
hb_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(hb_handler)

permissions = [
    ('Admin','admin'),
    ('Read Profile','read:profile'),
    ('Update Profile and Password','write:profile'),
    ('Read Projects','read:projects'),
    ('Create/Update Projects','write:projects'),
    ('Delete Projects','delete:projects'),
    ('Process Projects','process:projects'),
    ('Read Fields','read:fields'),
    ('Create/Update Fields','write:fields'),
    ('Delete Fields','delete:fields'),
    ('Read Receipts','read:receipts'),
    ('Create/Update Receipts','write:receipts'),
    ('Read Data','read:data'),
    ('Export Data','export:data'),
]

subscription_plans = [
    ('Standard Monthly','1k invoices per month',10.00, "KES","monthly",0,"ACTIVE"),
    ('Standard Annually','1.1k invoices per month',8, "KES","annually",0,"ACTIVE")
]