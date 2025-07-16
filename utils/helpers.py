import hashlib
import hmac
import re
import secrets
from typing import List, Tuple, Optional
from fastapi import HTTPException, Request, UploadFile
from pathlib import Path
import resend
import requests
import contextvars

from config import settings, logger

resend.api_key = settings.resend_api_key
request_context: contextvars.ContextVar[Optional[Request]] = contextvars.ContextVar('request', default=None)

def get_current_request() -> Optional[Request]:
    """Helper function to get the current request from context"""
    return request_context.get()

def set_current_request(request: Request) -> None:
    """Helper function to set the current request in context"""
    request_context.set(request)

def generate_reset_token(length: int = 32) -> str:
    """Generate a cryptographically secure reset token"""
    return secrets.token_urlsafe(length)

def hash_token(token: str) -> str:
    """Hash the token for secure storage"""
    return hashlib.sha256(token.encode()).hexdigest()

def send_email(to: Tuple[str,str], subject: str, message: str) -> bool:
    try:
        to_email,to_name = to
        params: resend.Emails.SendParams = {
            "from": settings.email_from,
            "reply_to": [settings.email_reply_to],
            "to": [f"{to_name} <{to_email}>"],
            "subject": subject,
            "html": message
        }
        email = resend.Emails.send(params)
        logger.info(f"send_email response {email}")
    except Exception as e:
        logger.error(e)
        raise e
    
async def send_verification_email(name: str, email: str, verification_code: str):
    """
    Send verification email using Mailtrap
    """
    try:
        subject = "Verify your ReceiptIQ account"
        message = f"""
        Welcome to ReceiptIQ!

        Your verification code is: {verification_code}

        This code will expire in {settings.otp_expiry_seconds // 60} minutes.

        If you didn't request this verification code, please ignore this email.

        Best regards,
        The ReceiptIQ Team
        """
        
        send_email(
            to=(email, name),  # Use part before @ as name
            subject=subject,
            message=message
        )
    except Exception as e:
        return False
    
async def send_password_reset_email(email: str, reset_token: str):
    """
    Send verification email using Mailtrap
    """
    reset_link = f"{settings.frontend_url}/password/reset?token={reset_token}&email={email}"
    try:
        subject = "ReceiptIQ - Password Reset Request"
        message = f"""
        Hi,

        You requested a password reset for your account.
    
        Click the link below to reset your password:

        <a href='{reset_link}'>Reset Password</a>
        
        This link will expire in {settings.password_reset_token_expiry_seconds // 60} minutes.

        If you didn't request this reset, please ignore this email.

        Best regards,
        The ReceiptIQ Team
        """
        
        send_email(
            to=(email, email.split('@')[0]),
            subject=subject,
            message=message
        )
    except Exception as e:
        return False

async def save_upload_file(upload_file: UploadFile, project_id: str) -> tuple[str, str]:
    """
    Save an uploaded file to the project's upload directory
    
    Args:
        upload_file: The uploaded file
        project_id: The project ID to create a subdirectory for
        
    Returns:
        tuple[str, str]: (file_path, file_name)
    """
    # Create project directory if it doesn't exist
    upload_dir = Path("uploads") / str(project_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate a unique filename to prevent collisions
    file_name = f"{upload_file.filename}"
    file_path = str(upload_dir / file_name)
    
    # Save the file
    with open(file_path, "wb") as f:
        content = await upload_file.read()
        f.write(content)
    
    return file_path, file_name

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
    
def create_paystack_subscription_plan(name: str, interval: str, amount: int, currency: str):
    url=f"{settings.paystack_base_url}/plan"
    headers={
        "Authorization": f"Bearer {settings.paystack_secret_key}",
        "Content-Type": "application/json"
    }
    data={ 
        "name": name, 
        "interval": interval, 
        "amount": amount*100,
        "currency": currency,
    }
    response = requests.post(
        url=url,
        headers=headers,
        json=data
    )
    logger.debug(f"create_paystack_subscription_plan response: {response.status_code} {response.json()}")
    if response.ok and response.json()["status"] == True:
        return response.json()["data"]
    else:
        raise Exception(response.text)
    
def get_paystack_plans():
    url=f"{settings.paystack_base_url}/plan"
    headers={
        "Authorization": f"Bearer {settings.paystack_secret_key}",
        "Content-Type": "application/json"
    }
    response = requests.get(
        url=url,
        headers=headers
    )
    logger.debug(f"get_paystack_plans response: {response.status_code} {response.json()}")
    if response.ok and response.json()["status"] == True:
        return response.json()["data"]
    else:
        raise Exception(response.text)
    
async def initiate_paystack_payment(email: str, amount: float, currency: str, plan:str):
    """
        Initiates paystack payment
    """
    url=f"{settings.paystack_base_url}/transaction/initialize"
    headers={
        "Authorization": f"Bearer {settings.paystack_secret_key}",
        "Content-Type": "application/json"
    }
    data={ 
        "email": f"{email}", 
        "amount": f"{amount*100}",
        "currency": f"{currency}",
        "plan": f"{plan}"
    }
    response = requests.post(
        url=url,
        headers=headers,
        json=data
    )
    logger.debug(f"initiate_paystack_payment response {response.status_code} {response.json()}")
    if response.ok and response.json()["status"]:
        return response.json()["data"]
    else:
        raise Exception(response.text)
    
async def get_paystack_subscription_link(subscription_code: str):
    """
        Gets paystack subscription management link
    """
    url=f"{settings.paystack_base_url}/subscription/{subscription_code}/manage/link"
    headers={
        "Authorization": f"Bearer {settings.paystack_secret_key}",
        "Content-Type": "application/json"
    }
    response = requests.get(
        url=url,
        headers=headers
    )
    logger.debug(f"get_paystack_subscription_link response {response.status_code} {response.json()}")
    if response.ok and response.json()["status"]:
        return response.json()["data"]
    else:
        raise Exception(response.text)
    

async def verify_paystack_signature(request: Request):   
    signature = request.headers.get("x-paystack-signature")
    if not signature:
        logger.warning(f"Paystack playload signature `x-paystack-signature` not found")
        raise HTTPException(status_code=400, detail="Missing signature")
    body = await request.body()
    hash_value = hmac.new(
        settings.paystack_secret_key.encode('utf-8'),
        body,
        hashlib.sha512
    ).hexdigest()
    if not hash_value == signature:
        logger.warning(f"Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

