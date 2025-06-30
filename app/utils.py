import hashlib
import random
import secrets
import string
from typing import Tuple
from fastapi import UploadFile
from pathlib import Path
import resend
from .config import settings, logger

resend.api_key = settings.resend_api_key

def random_string(length: int = 5) -> str:
    """Generate a random string of fixed length"""
    letters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(letters) for _ in range(length))

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
    reset_link = f"{settings.frontend_url}/reset-password?token={reset_token}"
    try:
        subject = "ReceiptIQ - Password Reset Request"
        message = f"""
        Hi,

        You requested a password reset for your account.
    
        Click the link below to reset your password:
        
        {reset_link}
        
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