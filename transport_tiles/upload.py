"""Uploads the generated tiles to the S3 bucket (Exoscale SOS).

S3_ENDPOINT, S3_BUCKET, S3_KEY (default transport.pmtiles),
S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY
"""

import os
import sys

import boto3
from boto3.s3.transfer import TransferConfig


def main(path):
    client = boto3.client(
        's3',
        endpoint_url=os.environ['S3_ENDPOINT'],
        aws_access_key_id=os.environ['S3_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['S3_SECRET_ACCESS_KEY'],
    )
    key = os.environ.get('S3_KEY', 'transport.pmtiles')
    client.upload_file(
        path,
        os.environ['S3_BUCKET'],
        key,
        ExtraArgs={
            'ACL': 'public-read',
            'ContentType': 'application/octet-stream',
            'CacheControl': 'public, max-age=3600',
        },
        Config=TransferConfig(multipart_chunksize=16 * 1024 * 1024),
    )
    print(f'uploaded {key}')


if __name__ == '__main__':
    main(sys.argv[1])
