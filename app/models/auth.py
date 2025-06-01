import datetime
from typing import List, Optional, Tuple
import uuid
from fastapi import HTTPException
import jwt
from mongoengine import (
    Document, StringField, BooleanField, DateTimeField, 
    ReferenceField, ListField, UUIDField, CASCADE
)
from app.utils import random_string
from app.config import logger

class Permission(Document):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    name = StringField(max_length=100, required=True)
    codename = StringField(max_length=100, required=True, unique=True)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField()

    meta = {
        'collection': 'permissions',
        'indexes': ['codename']
    }

class User(Document):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    first_name = StringField(max_length=100, required=True)
    last_name = StringField(max_length=100, required=True)
    email = StringField(max_length=100, required=True, unique=True)
    verification_code = StringField(max_length=5)
    verification_code_expiry_at = DateTimeField()
    is_active = BooleanField(default=False)
    is_verified = BooleanField(default=False)
    access_token = StringField(max_length=500)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField()
    permissions = ListField(ReferenceField(Permission, reverse_delete_rule=CASCADE))

    meta = {
        'collection': 'users',
        'indexes': ['email']
    }

    async def create_verification_code(self, code_length: int, code_expiry_seconds: int) -> "User":
        """
        Create the verification code for the user and set it's expiry date and time
        """
        code = random_string(length=code_length)
        expiry_at = datetime.datetime.now() + datetime.timedelta(seconds=code_expiry_seconds)
        self.verification_code = code
        self.verification_code_expiry_at = expiry_at
        self.save()
        logger.info(f"User {self.first_name} verification code {code} created, expires at {expiry_at}")
        return self

    async def validate_verification_code(self, code: str) -> bool:
        """
        Validate the verification code and activate the user
        """
        logger.info(f"User {self.first_name} verification code {code} vs {self.verification_code} verification requested at {datetime.datetime.now()} vs {self.verification_code_expiry_at}")
        if self.verification_code == code and self.verification_code_expiry_at > datetime.datetime.now():
            self.is_verified = True
            self.is_active = True
            self.verification_code = None
            self.verification_code_expiry_at = None
            self.save()
            logger.info(f"User {self.first_name} verified successfully")
            return True
        else:
            logger.info(f"User {self.first_name} verification failed")
            return False
    
    async def has_perm(self, permission_codename: str) -> bool:
        """
        Check if the user has the permission
        """
        for perm in self.permissions:
            if perm.codename == permission_codename:
                return True
        return False
    
    def __str__(self):
        return f"{self.first_name} - {self.email}"

    def create_jwt_token(self, secret: str, algorithm: str, expiry_seconds: int) -> str:
        """
        Create a JWT token for the user, encoding the email, user_id and expiry time and return it
        """
        logger.info(f"Creating JWT token for user {self.email}")
        expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expiry_seconds)
        payload = {
            "sub": self.email,
            "user_id": str(self.id),
            "exp": expire
        }
        return jwt.encode(payload=payload, key=secret, algorithm=algorithm)
    
    @staticmethod
    def verify_jwt_token(token: str, secret: str, algorithm: str) -> Tuple[str, str, str] | None:
        """
        Verify the JWT token and return the email and user_id
        """
        logger.info(f"Verifying JWT token {token}")
        try:
            payload = jwt.decode(jwt=token, key=secret, algorithms=[algorithm], options={"verify_exp": True, "verify_signature": True, "required": ["exp", "sub"]})
            return payload.get("sub", None), payload.get("user_id", None)
        except jwt.InvalidAlgorithmError:
            logger.error(f"JWT token invalid algorithm: {algorithm} on token: {token}")
            raise HTTPException(status_code=401, detail={"message": "Invalid access token"})
        except jwt.ExpiredSignatureError:
            logger.error(f"JWT expired signature on token: {token}")
            raise HTTPException(status_code=401, detail={"message": "Access Token expired"})
        except jwt.InvalidTokenError as e:
            logger.error(f"JWT invalid token: {token} error: {e}")
            raise HTTPException(status_code=401, detail={"message": "Invalid access token"})