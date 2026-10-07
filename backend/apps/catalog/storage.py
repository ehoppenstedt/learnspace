"""Object storage behind one small interface.

- "s3": any S3-compatible bucket (Cloudflare R2, AWS S3). Presigned PUT for uploads, presigned
  GET for reads, so the bucket stays private ("signed URLs for media").
- "local": development. Files on disk; uploads and reads go through Django views protected
  with short-lived signed tokens that mimic presigned URLs.
"""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.core import signing

_SALT = "media-url"


class Storage:
    def presigned_put(self, key: str, content_type: str, max_bytes: int) -> dict:
        raise NotImplementedError

    def url(self, key: str) -> str:
        raise NotImplementedError

    def read(self, key: str) -> bytes:
        raise NotImplementedError

    def write(self, key: str, data: bytes, content_type: str) -> None:
        raise NotImplementedError

    def size(self, key: str) -> int | None:
        raise NotImplementedError

    def local_path(self, key: str) -> Path | None:
        return None


class LocalStorage(Storage):
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Invalid key")
        return path

    def _signed(self, action: str, key: str, **extra) -> str:
        token = signing.dumps({"k": key, "a": action, **extra}, salt=_SALT)
        return f"{settings.PUBLIC_BASE_URL}/media-local/{action}?{urlencode({'t': token})}"

    def presigned_put(self, key, content_type, max_bytes):
        return {"method": "PUT", "url": self._signed("put", key, ct=content_type, max=max_bytes),
                "headers": {"Content-Type": content_type}}

    def url(self, key):
        return self._signed("get", key)

    def read(self, key):
        return self._path(key).read_bytes()

    def write(self, key, data, content_type):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def size(self, key):
        path = self._path(key)
        return path.stat().st_size if path.exists() else None

    def local_path(self, key):
        return self._path(key)

    @staticmethod
    def unsign(token: str, action: str, max_age: int) -> dict:
        data = signing.loads(token, salt=_SALT, max_age=max_age)
        if data.get("a") != action:
            raise signing.BadSignature("wrong action")
        return data


class S3Storage(Storage):
    def __init__(self):
        import boto3
        from botocore.config import Config

        self.bucket = settings.S3_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            region_name=settings.S3_REGION,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
        )

    def presigned_put(self, key, content_type, max_bytes):
        url = self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=settings.MEDIA_UPLOAD_URL_TTL,
        )
        # Size is enforced again server-side in complete_upload (HEAD) before processing.
        return {"method": "PUT", "url": url, "headers": {"Content-Type": content_type}}

    def url(self, key):
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=settings.MEDIA_READ_URL_TTL
        )

    def read(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def write(self, key, data, content_type):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                               CacheControl="private, max-age=31536000, immutable")

    def size(self, key):
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"]
        except self.client.exceptions.ClientError:
            return None


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    if settings.MEDIA_STORAGE == "s3":
        return S3Storage()
    return LocalStorage(settings.MEDIA_ROOT)
