import os
import boto3
from botocore.exceptions import ClientError
from typing import BinaryIO
from uuid import UUID, uuid4
from datetime import datetime
from config import get_settings

class StorageService:
    def __init__(self):
        pass
    
    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        try:
            self.s3.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                try:
                    self.s3.create_bucket(Bucket=self.bucket_name)
                    print(f"Created bucket: {self.bucket_name}")
                except ClientError as create_error:
                    print(f"Error creating bucket: {create_error}")
            else:
                print(f"Error checking bucket: {e}")
    
    def upload_receipt(self, project_id: UUID, file: BinaryIO, filename: str) -> str:
        """Upload receipt file and return the object key"""
        settings = get_settings()
        self.s3 = boto3.client(
            's3',
            endpoint_url=settings.aws_endpoint_url_s3 or None,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region or None
        )
        self.bucket_name = settings.bucket_name
        self._ensure_bucket_exists()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        object_key = f"{settings.environment}/receipts/{str(project_id)}/{uuid4()}_{timestamp}_{filename}"
        
        try:
            self.s3.upload_fileobj(
                file,
                self.bucket_name,
                object_key,
                ExtraArgs={
                    'ContentType': 'application/octet-stream',
                    'Metadata': {
                        'project_id': str(project_id),
                        'original_filename': filename,
                        'upload_timestamp': datetime.now().isoformat()
                    }
                }
            )
            return object_key
        except ClientError as e:
            print(e)
            raise Exception(f"Failed to upload receipt: {e}")
        
    def upload_export(self, project_id: UUID, file: BinaryIO, filename: str) -> str:
        """Upload receipt file and return the object key"""
        settings = get_settings()
        self.s3 = boto3.client(
            's3',
            endpoint_url=settings.aws_endpoint_url_s3 or None,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region or None
        )
        self.bucket_name = settings.bucket_name
        self._ensure_bucket_exists()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        object_key = f"{settings.environment}/exports/{str(project_id)}/{uuid4()}_{timestamp}_{filename}"
        
        try:
            self.s3.upload_fileobj(
                file,
                self.bucket_name,
                object_key,
                ExtraArgs={
                    'ContentType': 'application/octet-stream',
                    'Metadata': {
                        'project_id': str(project_id),
                        'original_filename': filename,
                        'upload_timestamp': datetime.now().isoformat()
                    }
                }
            )
            return object_key
        except ClientError as e:
            raise Exception(f"Failed to upload export file: {e}")
    
    def get_url(self, object_key: str) -> str:
        """Generate presigned URL for receipt download"""
        settings = get_settings()
        self.s3 = boto3.client(
            's3',
            endpoint_url=settings.aws_endpoint_url_s3 or None,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region or None
        )
        self.bucket_name = settings.bucket_name
        self._ensure_bucket_exists()
        try:
            url = self.s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': object_key},
                ExpiresIn=3600
            )
            return url
        except ClientError as e:
            raise Exception(f"Failed to generate download URL: {e}")
    
    def delete_receipt(self, object_key: str) -> bool:
        """Delete a receipt file"""
        settings = get_settings()
        self.s3 = boto3.client(
            's3',
            endpoint_url=settings.aws_endpoint_url_s3 or None,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region or None
        )
        self.bucket_name = settings.bucket_name
        self._ensure_bucket_exists()
        try:
            self.s3.delete_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError as e:
            print(f"Error deleting receipt: {e}")
            return False
    
    def download_file(self, object_key: str, local_path: str):
        """Download a file"""
        settings = get_settings()
        # print(settings)       
        self.s3 = boto3.client(
            's3',
            endpoint_url=settings.aws_endpoint_url_s3 or None,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region or None
        )
        self.bucket_name = settings.bucket_name
        self._ensure_bucket_exists()
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            self.s3.download_file(self.bucket_name, object_key, local_path)
            return True
        except ClientError as e:
            print(f"Error downloading file: {e}")
            return False