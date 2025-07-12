import base64
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import select
from sqlalchemy.orm import Session
from models import User, Permission, PasswordResetToken, RefreshToken, RevokedToken
from utils import hash_token, generate_reset_token
import datetime
import hashlib


class TestAuthEndpoints:
    
    def setup_method(self):
        """Setup common test data"""
        self.test_user_data = {
            "first_name": "John",
            "last_name": "Doe", 
            "email": "kahenya0@gmail.com",
            "password": "SuperS3cr3t@Pass"
        }
        
    def get_auth_headers(self, test_settings):
        """Helper to get client auth headers"""
        credentials = base64.b64encode(f"{test_settings.client_id}:{test_settings.client_secret}".encode()).decode()
        return {"Authorization": f"Basic {credentials}"}

    @patch("api.auth.send_verification_email")
    def test_signup(self, mock_send_email, client, test_settings, db):
        """Test user signup - success and failure scenarios"""
        mock_send_email.return_value = True
        headers = self.get_auth_headers(test_settings)
        
        # Test successful signup
        response = client.post(
            url="/api/v1/auth/signup",
            json=self.test_user_data,
            headers=headers
        )
        assert response.status_code == 201
        assert response.json()["message"] == "User created successfully. Check your email for otp code"
        assert "user" in response.json()
        
        # Test duplicate email
        response = client.post(
            url="/api/v1/auth/signup",
            json=self.test_user_data,
            headers=headers
        )
        assert response.status_code == 400
        assert f"User with email {self.test_user_data['email']} already exists" in response.json()["detail"]
        
        # Test weak password
        weak_password_data = self.test_user_data.copy()
        weak_password_data["password"] = "weak"
        weak_password_data["email"] = "weak@example.com"
        
        response = client.post(
            url="/api/v1/auth/signup",
            json=weak_password_data,
            headers=headers
        )
        assert response.status_code == 422

    @patch("api.auth.send_verification_email")
    def test_get_otp(self, mock_send_email, client, test_settings, db):
        """Test OTP generation - success and failure scenarios"""
        mock_send_email.return_value = True
        headers = self.get_auth_headers(test_settings)
        
        user = User(
            first_name=self.test_user_data["first_name"],
            last_name=self.test_user_data["last_name"],
            email=self.test_user_data["email"]
        )
        user.set_password(self.test_user_data["password"])
        db.add(user)
        db.commit()
        
        # Test successful OTP request
        response = client.post(
            url="/api/v1/auth/otp/get",
            json={"email": self.test_user_data["email"]},
            headers=headers
        )
        assert response.status_code == 200
        assert f"OTP code sent to {self.test_user_data['email']}" in response.json()["message"]
        
        # Test OTP request for non-existent user
        response = client.post(
            url="/api/v1/auth/otp/get",
            json={"email": "nonexistent@example.com"},
            headers=headers
        )
        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    def test_check_otp(self, client, test_settings, db):
        """Test OTP verification - success and failure scenarios"""
        headers = self.get_auth_headers(test_settings)
        
        user = User(
            first_name=self.test_user_data["first_name"],
            last_name=self.test_user_data["last_name"],
            email=self.test_user_data["email"]
        )
        user.set_password(self.test_user_data["password"])
        permission = db.execute(select(Permission).where(Permission.codename == "read:profile")).scalar_one_or_none()        
        user.scopes.append(permission)
        db.add(user)
        db.commit()
        user.otp = "12345"
        user.otp_expiry_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
        db.commit()
        
        # Test successful OTP verification
        response = client.post(
            url="/api/v1/auth/otp/check",
            json={"email": self.test_user_data["email"], "code": "12345"},
            headers=headers
        )
        assert response.status_code == 200
        assert "User Email Verified" in response.json()["message"]
        
        # Test invalid OTP
        response = client.post(
            url="/api/v1/auth/otp/check",
            json={"email": self.test_user_data["email"], "code": "wrong"},
            headers=headers
        )
        assert response.status_code == 400
        assert "Invalid or expired otp code" in response.json()["detail"]
        
        # Test non-existent user
        response = client.post(
            url="/api/v1/auth/otp/check",
            json={"email": "nonexistent@example.com", "code": "12345"},
            headers=headers
        )
        assert response.status_code == 404
        assert "Missing or Deactivated User" in response.json()["detail"]

    def test_token_login(self, client, test_settings, db):
        """Test login token endpoint - success and failure scenarios"""
        headers = self.get_auth_headers(test_settings)
        
        # Create verified user
        user = User(
            first_name=self.test_user_data["first_name"],
            last_name=self.test_user_data["last_name"],
            email=self.test_user_data["email"],
            is_verified=True,
            is_active=True
        )
        user.set_password(self.test_user_data["password"])
        permission = db.execute(select(Permission).where(Permission.codename == "read:profile")).scalar_one_or_none()        
        user.scopes.append(permission)
        db.add(user)
        db.commit()

        response = client.post(
            url="/api/v1/auth/token",
            data={
                "username": self.test_user_data["email"],
                "password": self.test_user_data["password"],
                "grant_type": "password"
            },
            headers=headers
        )
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert "refresh_token" in response.json()
        assert response.json()["token_type"] == "Bearer"
        
        # Test invalid credentials
        response = client.post(
            url="/api/v1/auth/token",
            data={
                "username": self.test_user_data["email"],
                "password": "wrongpassword",
                "grant_type": "password"
            },
            headers=headers
        )
        assert response.status_code == 401
        assert "Invalid Username or Password" in response.json()["detail"]
        
        # Test unverified user
        user.is_verified = False
        db.commit()
        
        response = client.post(
            url="/api/v1/auth/token",
            data={
                "username": self.test_user_data["email"],
                "password": self.test_user_data["password"],
                "grant_type": "password"
            },
            headers=headers
        )
        assert response.status_code == 400
        assert "User not verified" in response.json()["detail"]
        
        # Test inactive user
        user.is_verified = True
        user.is_active = False
        db.commit()
        
        response = client.post(
            url="/api/v1/auth/token",
            data={
                "username": self.test_user_data["email"],
                "password": self.test_user_data["password"],
                "grant_type": "password"
            },
            headers=headers
        )
        assert response.status_code == 400
        assert "Inactive user" in response.json()["detail"]
        
        # Test unsupported grant type
        user.is_active = True
        db.commit()
        
        response = client.post(
            url="/api/v1/auth/token",
            data={
                "username": self.test_user_data["email"],
                "password": self.test_user_data["password"],
                "grant_type": "authorization_code"
            },
            headers=headers
        )
        assert response.status_code == 400
        assert "unsupported_grant_type" in response.json()["detail"]["error"]

    def test_refresh_token(self, client, test_settings, db):
        """Test token refresh - success and failure scenarios"""
        headers = self.get_auth_headers(test_settings)
        
        # Create verified user
        user = User(
            first_name=self.test_user_data["first_name"],
            last_name=self.test_user_data["last_name"],
            email=self.test_user_data["email"],
            is_verified=True,
            is_active=True
        )
        user.set_password(self.test_user_data["password"])
        db.add(user)
        db.commit()
        
        # Create refresh token
        refresh_token = user.create_refresh_token(db)
        
        # Test successful refresh
        response = client.post(
            url="/api/v1/auth/token/refresh",
            json={
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            },
            headers=headers
        )
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert "refresh_token" in response.json()
        
        # Test invalid refresh token
        response = client.post(
            url="/api/v1/auth/token/refresh",
            json={
                "refresh_token": "invalid_token",
                "grant_type": "refresh_token"
            },
            headers=headers
        )
        assert response.status_code == 401
        assert "invalid_grant" in response.json()["detail"]["error"]
        
        # Test unsupported grant type
        response = client.post(
            url="/api/v1/auth/token/refresh",
            json={
                "refresh_token": refresh_token,
                "grant_type": "password"
            },
            headers=headers
        )
        assert response.status_code == 422

    def test_revoke_token(self, client, test_settings, db):
        """Test token revocation - success scenarios"""
        headers = self.get_auth_headers(test_settings)
        
        # Create user and tokens
        user = User(
            first_name=self.test_user_data["first_name"],
            last_name=self.test_user_data["last_name"],
            email=self.test_user_data["email"],
            is_verified=True,
            is_active=True
        )
        user.set_password(self.test_user_data["password"])
        db.add(user)
        db.commit()
        
        access_token = user.create_jwt_token(
            secret=test_settings.secret_key,
            algorithm=test_settings.algorithm,
            expiry_seconds=test_settings.access_token_expiry_seconds
        )
        refresh_token = user.create_refresh_token(db)
        
        # Test revoking access token
        response = client.post(
            url="/api/v1/auth/token/revoke",
            json={
                "token": access_token,
                "token_type_hint": "access_token"
            },
            headers=headers
        )
        assert response.status_code == 200
        assert "Token revocation successful" in response.json()["message"]
        
        # Test revoking refresh token
        response = client.post(
            url="/api/v1/auth/token/revoke",
            json={
                "token": refresh_token,
                "token_type_hint": "refresh_token"
            },
            headers=headers
        )
        assert response.status_code == 200
        assert "Token revocation successful" in response.json()["message"]

    @patch("api.auth.send_password_reset_email")
    def test_forgot_password(self, mock_send_email, client, test_settings, db):
        """Test forgot password - success and failure scenarios"""
        mock_send_email.return_value = True
        headers = self.get_auth_headers(test_settings)
        
        # Create user
        user = User(
            first_name=self.test_user_data["first_name"],
            last_name=self.test_user_data["last_name"],
            email=self.test_user_data["email"]
        )
        user.set_password(self.test_user_data["password"])
        db.add(user)
        db.commit()
        
        # Test successful forgot password
        response = client.post(
            url="/api/v1/auth/password/forgot",
            json={"email": self.test_user_data["email"]},
            headers=headers
        )
        assert response.status_code == 200
        assert "password reset link" in response.json()["message"]
        
        # Test non-existent user
        response = client.post(
            url="/api/v1/auth/password/forgot",
            json={"email": "nonexistent@example.com"},
            headers=headers
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"]

    def test_reset_password(self, client, test_settings, db):
        """Test password reset - success and failure scenarios"""
        headers = self.get_auth_headers(test_settings)
        
        # Create user
        user = User(
            first_name=self.test_user_data["first_name"],
            last_name=self.test_user_data["last_name"],
            email=self.test_user_data["email"]
        )
        user.set_password(self.test_user_data["password"])
        db.add(user)
        db.commit()
        
        # Create reset token
        reset_token = generate_reset_token(32)
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        
        password_reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(reset_token),
            expires_at=expires_at
        )
        db.add(password_reset_token)
        db.commit()
        
        # Test successful password reset
        response = client.post(
            url="/api/v1/auth/password/reset",
            json={
                "email": self.test_user_data["email"],
                "token": reset_token,
                "new_password": "NewS3cr3t@Pass"
            },
            headers=headers
        )
        assert response.status_code == 200
        assert "Password has been reset successfully" in response.json()["message"]
        
        # Test invalid token
        response = client.post(
            url="/api/v1/auth/password/reset",
            json={
                "email": self.test_user_data["email"],
                "token": "invalid_token",
                "new_password": "NewS3cr3t@Pass"
            },
            headers=headers
        )
        assert response.status_code == 403
        assert "Invalid or Expired Reset Token" in response.json()["detail"]

    def test_change_password(self, client, test_settings, db):
        """Test password change - success and failure scenarios"""
        headers = self.get_auth_headers(test_settings)
        
        # Create verified user with permissions
        user = User(
            first_name=self.test_user_data["first_name"],
            last_name=self.test_user_data["last_name"],
            email=self.test_user_data["email"],
            is_verified=True,
            is_active=True
        )
        user.set_password(self.test_user_data["password"])
        
        # Add required permission
        permission = db.execute(select(Permission).where(Permission.codename == "write:profile")).scalar_one_or_none()        
        user.scopes.append(permission)
        db.add(user)
        db.commit()
        
        # Get access token
        access_token = user.create_jwt_token(
            secret=test_settings.secret_key,
            algorithm=test_settings.algorithm,
            expiry_seconds=test_settings.access_token_expiry_seconds,
            granted_scopes=["write:profile"]
        )
        
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        
        # Test successful password change
        response = client.post(
            url="/api/v1/auth/password/change",
            json={
                "current_password": self.test_user_data["password"],
                "new_password": "NewS3cr3t@Pass"
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        assert "Password has been updated successfully" in response.json()["message"]
        
        # Test incorrect current password
        response = client.post(
            url="/api/v1/auth/password/change",
            json={
                "current_password": "wrongpassword",
                "new_password": "AnotherS3cr3t@Pass"
            },
            headers=auth_headers
        )
        assert response.status_code == 401
        assert "Incorrect current password" in response.json()["detail"]
        
        # Test weak new password
        response = client.post(
            url="/api/v1/auth/password/change",
            json={
                "current_password": "NewS3cr3t@Pass",
                "new_password": "weak"
            },
            headers=auth_headers
        )
        assert response.status_code == 422

    def test_get_user_profile(self, client, test_settings, db):
        """Test get user profile - success and failure scenarios"""
        # Create verified user with permissions
        user = User(
            first_name=self.test_user_data["first_name"],
            last_name=self.test_user_data["last_name"],
            email=self.test_user_data["email"],
            is_verified=True,
            is_active=True
        )
        user.set_password(self.test_user_data["password"])
        
        # Add required permission
        permission = db.execute(select(Permission).where(Permission.codename == "read:profile")).scalar_one_or_none()        
        user.scopes.append(permission)
        db.add(user)
        db.commit()
        
        # Get access token
        access_token = user.create_jwt_token(
            secret=test_settings.secret_key,
            algorithm=test_settings.algorithm,
            expiry_seconds=test_settings.access_token_expiry_seconds,
            granted_scopes=["read:profile"]
        )
        
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        
        # Test successful profile retrieval
        response = client.get(
            url="/api/v1/auth/me",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["email"] == self.test_user_data["email"]
        assert response.json()["first_name"] == self.test_user_data["first_name"]
        
        # Test without authorization
        response = client.get(url="/api/v1/auth/me")
        assert response.status_code == 401

    @patch("api.auth.send_verification_email")
    def test_update_user_profile(self, mock_send_email, client, test_settings, db):
        """Test update user profile - success and failure scenarios"""
        mock_send_email.return_value = True
        
        # Create verified user with permissions
        user = User(
            first_name=self.test_user_data["first_name"],
            last_name=self.test_user_data["last_name"],
            email=self.test_user_data["email"],
            is_verified=True,
            is_active=True
        )
        user.set_password(self.test_user_data["password"])
        
        # Add required permission
        permission = db.execute(select(Permission).where(Permission.codename == "write:profile")).scalar_one_or_none()        
        user.scopes.append(permission)
        db.add(user)
        db.commit()
        
        # Get access token
        access_token = user.create_jwt_token(
            secret=test_settings.secret_key,
            algorithm=test_settings.algorithm,
            expiry_seconds=test_settings.access_token_expiry_seconds,
            granted_scopes=["write:profile"]
        )
        
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        
        # Test successful profile update
        response = client.patch(
            url="/api/v1/auth/me",
            json={
                "first_name": "Jane",
                "last_name": "Smith"
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        assert "User updated successfully" in response.json()["message"]
        assert response.json()["user"]["first_name"] == "Jane"
        
        # Test email update (should trigger verification)
        response = client.patch(
            url="/api/v1/auth/me",
            json={
                "email": "jane.smith@example.com"
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        assert "new email needs to be verified" in response.json()["message"]
        
        # Test without authorization
        response = client.patch(
            url="/api/v1/auth/me",
            json={"first_name": "Test"},
        )
        assert response.status_code == 401

    def test_logout(self, client, test_settings, db):
        """Test user logout - success and failure scenarios"""
        # Create verified user
        user = User(
            first_name=self.test_user_data["first_name"],
            last_name=self.test_user_data["last_name"],
            email=self.test_user_data["email"],
            is_verified=True,
            is_active=True
        )
        user.set_password(self.test_user_data["password"])
        db.add(user)
        db.commit()
        
        # Get access token
        access_token = user.create_jwt_token(
            secret=test_settings.secret_key,
            algorithm=test_settings.algorithm,
            expiry_seconds=test_settings.access_token_expiry_seconds
        )
        
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        
        # Test successful logout
        response = client.post(
            url="/api/v1/auth/logout",
            data={"token": access_token},
            headers=auth_headers
        )
        assert response.status_code == 200
        assert "Logout successful" in response.json()["message"]
        
        # Test logout without token
        response = client.post(
            url="/api/v1/auth/logout",
            data={},
            headers=auth_headers
        )
        assert response.status_code == 401