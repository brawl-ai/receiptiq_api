import logging
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    environment: str = "development"
    project_name: str = "ReceiptIQ API"
    version: str = "0.0.1"
    api_v1_str: str = "/api/v1"
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expiry_seconds: int = 3600  # 1 hour
    otp_length: int = 5 
    otp_expiry_seconds: int  = 300  # 5 minutes
    password_reset_token_length: int = 32
    password_reset_token_expiry_seconds: int = 300
    refresh_token_length: int = 128
    refresh_token_expiry_seconds: int = 2592000 # 30 days
    frontend_url: str = ""
    postgres_user: str = ""
    postgres_password: str = ""
    postgres_db: str = ""
    postgres_host: str = ""
    postgres_port: str = "5842"
    admin_email: str = ""
    admin_password: str = ""
    joe_email: str = ""
    joe_password: str = ""
    openai_api_key: str = "testapi"
    client_id: str = ""
    client_secret: str = ""
    resend_api_key: str = ""
    email_from: str = ""
    email_reply_to: str = ""
    paystack_secret_key: str = ""
    paystack_base_url: str = ""
    aws_access_key_id: str = ""
    aws_endpoint_url_s3: str = ""
    aws_region: str = ""
    aws_secret_access_key: str = ""
    bucket_name: str = ""
    celery_broker_url: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    
    @property
    def database_url(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

settings = Settings()

logger = logging.getLogger('ReceiptIQ')
file_handler = logging.FileHandler("receiptiq.log", encoding="utf-8")
file_handler.setLevel(logging.ERROR)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

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
    ('Delete Receipts','delete:receipts'),
    ('Read Data','read:data'),
    ('Update Data','write:data'),
    ('Export Data','export:data'),
]

subscription_plans = [
    ('Free Trial', 'Get a taste of ReceiptIQ - up to 1,000 invoices/month', 0.00, "USD", "monthly", 30, "ACTIVE", [
        "Up to 1,000 invoices/month",
        "1 project",
        "Custom Schema"
    ],1000),
    ('Pro Monthly', 'For freelancers & small teams — up to 5,000 invoices/month', 5.00, "USD", "monthly", 0, "ACTIVE", [
        "Everything in Free Trial",
        "5,000 invoices/month",
        "Unlimited projects",
        "24/7 email support",
    ],5000),
    ('Pro Annual', 'For freelancers & small teams — up to 5,000 invoices/month', 48.00, "USD", "annually", 0, "ACTIVE",[
        "Everything in Free Trial",
        "5,000 invoices/month",
        "Unlimited projects",
        "24/7 email support",
    ],5000)
]

def get_settings():
    return Settings()
