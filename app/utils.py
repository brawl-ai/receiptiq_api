import random
import string
from typing import Tuple
import requests
import os
from fastapi import UploadFile
from pathlib import Path

from .config import settings, logger

def random_string(length: int = 5) -> str:
    """Generate a random string of fixed length"""
    letters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(letters) for _ in range(length))

def send_email(to: Tuple[str,str], subject: str, message: str) -> bool:
    try:
        pass
    except Exception as e:
        raise e
    
async def send_verification_email(email: str, verification_code: str):
    """
    Send verification email using Mailtrap
    """
    try:
        subject = "Verify your ReceiptIQ account"
        message = f"""
        Welcome to ReceiptIQ!

        Your verification code is: {verification_code}

        This code will expire in {settings.VERIFICATION_CODE_EXPIRY_SECONDS // 60} minutes.

        If you didn't request this verification code, please ignore this email.

        Best regards,
        The ReceiptIQ Team
        """
        
        send_email(
            to=(email, email.split('@')[0]),  # Use part before @ as name
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