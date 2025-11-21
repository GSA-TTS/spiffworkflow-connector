from typing import Optional
import boto3
from botocore.config import Config
from urllib.parse import urlparse
from config import s3_config

def create_s3_client(storage_url: Optional[str] = None):
    """Create an S3 client using either environment config or custom storage URL."""
    if storage_url:
        # Parse s3:// URL for custom storage
        parsed = urlparse(storage_url)
        if parsed.scheme != 's3':
            raise ValueError("Storage URL must use s3:// scheme")
        bucket = parsed.netloc
        
        # Use the bucket's region for the client
        s3 = boto3.client('s3')
        location = s3.get_bucket_location(Bucket=bucket)
        region = location['LocationConstraint'] or 'us-east-1'
    else:
        region = s3_config.region
        
    # Create base client configuration
    client_kwargs = {
        'aws_access_key_id': s3_config.access_key,
        'aws_secret_access_key': s3_config.secret_key,
        'config': Config(
            region_name=region,
            signature_version='s3v4',
        ),
    }
    
    # Add internal endpoint URL if specified (e.g., minio:9000 in Docker network)
    # This endpoint is used for internal operations like uploading files
    if s3_config.endpoint_url:
        client_kwargs['endpoint_url'] = s3_config.endpoint_url
        # Only disable SSL for local endpoints
        if 'localhost' in s3_config.endpoint_url:
            client_kwargs['use_ssl'] = False
    
    # Handle cases where internal and external endpoints differ:
    # 1. Docker: internal=minio:9000, external=localhost:9003
    # 2. AWS: internal=s3.us-east-1.amazonaws.com, external=bucket.s3.us-east-1.amazonaws.com
    # 3. Custom setups: internal=storage.internal, external=storage.public.example.com
    if s3_config.public_endpoint_url:
        # Create primary client for internal operations (upload, delete, etc)
        s3_client = boto3.client('s3', **client_kwargs)
        
        # Create a separate client just for generating publicly accessible URLs
        # This ensures URLs contain the correct endpoint that external users can access
        presigned_client_kwargs = client_kwargs.copy()
        presigned_client_kwargs['endpoint_url'] = s3_config.public_endpoint_url
        if 'localhost' in s3_config.public_endpoint_url:
            presigned_client_kwargs['use_ssl'] = False
        presigned_client = boto3.client('s3', **presigned_client_kwargs)
        
        # Override URL generation to always use the public endpoint
        # This way s3_client.generate_presigned_url() transparently works
        s3_client.generate_presigned_url = presigned_client.generate_presigned_url
        return s3_client
    
    return boto3.client('s3', **client_kwargs)

def get_bucket_for_storage(storage_url: Optional[str] = None) -> str:
    """Get the S3 bucket name from either storage URL or config."""
    if storage_url:
        parsed = urlparse(storage_url)
        return parsed.netloc
    return s3_config.bucket

def generate_private_link(bucket: str, key: str) -> str:
    """Generate a private s3:// URL for an object."""
    return f"s3://{bucket}/{key}"

def generate_presigned_url(s3_client, bucket: str, key: str) -> str:
    """Generate a presigned URL for an object."""
    return s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=s3_config.signed_link_expiration
    )
