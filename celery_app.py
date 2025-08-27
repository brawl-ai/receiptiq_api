import os
from typing import Tuple

import resend
from celery import Celery
from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import settings, logger

resend.api_key = settings.resend_api_key
app = Celery(
    "receiptiq",
    broker=settings.celery_broker_url,
    backend=settings.celery_broker_url
)

# Configure
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]) 
)

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

@app.task
def send_verification_email(name: str, email: str, verification_code: str):
    """
    Send verification email using Mailtrap
    """
    try:
        subject = "Verify your ReceiptIQ account"
        template = jinja_env.get_template("verification_email.html")
        message = template.render(
            name=name,
            verification_code=verification_code,
            expiry_minutes=settings.otp_expiry_seconds // 60
        )
        send_email(
            to=(email, name),
            subject=subject,
            message=message
        )
    except Exception as e:
        return False

@app.task
def send_password_reset_email(email: str, reset_token: str):
    """
    Send verification email using Mailtrap
    """
    reset_link = f"{settings.frontend_url}/password/reset?token={reset_token}&email={email}"
    try:
        subject = "ReceiptIQ - Password Reset Request"
        template = jinja_env.get_template("password_reset_email.html")
        message = template.render(
            name=email.split('@')[0],
            reset_link=reset_link,
            expiry_minutes=settings.password_reset_token_expiry_seconds // 60
        )
        send_email(
            to=(email, email.split('@')[0]),
            subject=subject,
            message=message
        )
    except Exception as e:
        return False
