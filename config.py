import os
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class S3Config:
    """Configuration for S3 access, supporting both environment variables and VCAP_SERVICES."""
    
    def __init__(self):
        # Get VCAP credentials once and store them
        self.vcap_creds = self._get_vcap_credentials()
        
        self.bucket = self._get_s3_bucket()
        self.region = self._get_s3_region()
        self.access_key = self._get_access_key()
        self.secret_key = self._get_secret_key()
        self.endpoint_url = os.getenv('S3_ENDPOINT_URL')  # Internal URL for operations
        self.public_endpoint_url = os.getenv('S3_PUBLIC_ENDPOINT_URL')  # Public URL for presigned links
        self.signed_link_expiration = int(os.getenv('SIGNED_LINK_EXPIRATION', '3600'))

    def _get_vcap_credentials(self) -> Optional[Dict[str, Any]]:
        """Get S3 credentials from VCAP_SERVICES if available."""
        vcap_services = os.getenv('VCAP_SERVICES')
        if not vcap_services:
            return None
            
        try:
            services = json.loads(vcap_services)
            # Look for an S3 service named "artifacts"
            for service_type, instances in services.items():
                for instance in instances:
                    if instance.get('name') == 'artifacts':
                        return instance.get('credentials')
        except json.JSONDecodeError:
            logger.warning("Failed to parse VCAP_SERVICES JSON")
        except Exception as e:
            logger.warning(f"Error processing VCAP_SERVICES: {e}")
            
        return None

    def _get_s3_bucket(self) -> str:
        """Get S3 bucket name from environment or VCAP_SERVICES."""
        bucket = os.getenv('S3_BUCKET')
        if not bucket and self.vcap_creds:
            bucket = self.vcap_creds.get('bucket')
        if not bucket:
            raise ValueError("S3_BUCKET must be set in environment or VCAP_SERVICES")
        return bucket

    def _get_s3_region(self) -> str:
        """Get AWS region from environment or VCAP_SERVICES."""
        region = os.getenv('S3_REGION')
        if not region and self.vcap_creds:
            region = self.vcap_creds.get('region')
        if not region:
            raise ValueError("S3_REGION must be set in environment or VCAP_SERVICES")
        return region

    def _get_access_key(self) -> str:
        """Get AWS access key from environment or VCAP_SERVICES."""
        key = os.getenv('AWS_ACCESS_KEY_ID')
        if not key and self.vcap_creds:
            key = self.vcap_creds.get('access_key_id')
        if not key:
            raise ValueError("AWS_ACCESS_KEY_ID must be set in environment or VCAP_SERVICES")
        return key

    def _get_secret_key(self) -> str:
        """Get AWS secret key from environment or VCAP_SERVICES."""
        key = os.getenv('AWS_SECRET_ACCESS_KEY')
        if not key and self.vcap_creds:
            key = self.vcap_creds.get('secret_access_key')
        if not key:
            raise ValueError("AWS_SECRET_ACCESS_KEY must be set in environment or VCAP_SERVICES")
        return key

# Global config instance
s3_config = S3Config()
