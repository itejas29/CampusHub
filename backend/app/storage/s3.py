from __future__ import annotations

from functools import cached_property

from app.storage.base import SavedObject, StorageBackend


class S3Storage(StorageBackend):
    """Production backend. boto3 is imported lazily so local development never
    needs AWS credentials present."""

    name = "s3"

    def __init__(self, bucket: str, region: str, public_base_url: str = "",
                 access_key: str = "", secret_key: str = "") -> None:
        self.bucket = bucket
        self.region = region
        self.public_base_url = public_base_url.rstrip("/")
        self._access_key = access_key
        self._secret_key = secret_key

    @cached_property
    def _client(self):  # pragma: no cover - requires AWS
        import boto3

        kwargs = {"region_name": self.region}
        # Prefer the instance/task IAM role; only fall back to static keys.
        if self._access_key and self._secret_key:
            kwargs |= {
                "aws_access_key_id": self._access_key,
                "aws_secret_access_key": self._secret_key,
            }
        return boto3.client("s3", **kwargs)

    def save(self, data: bytes, *, key: str, content_type: str) -> SavedObject:  # pragma: no cover
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data,
                                ContentType=content_type)
        return SavedObject(key=key, url=self.url(key), size_bytes=len(data),
                           content_type=content_type, backend=self.name)

    def url(self, key: str) -> str:  # pragma: no cover
        if self.public_base_url:  # CloudFront distribution in front of the bucket
            return f"{self.public_base_url}/{key}"
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=3600
        )

    def delete(self, key: str) -> None:  # pragma: no cover
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def open(self, key: str) -> bytes:  # pragma: no cover
        return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
