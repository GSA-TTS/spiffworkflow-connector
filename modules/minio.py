from minio import Minio
import os

client = Minio(
    "minio:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False,  # Set to True if using HTTPS
)
