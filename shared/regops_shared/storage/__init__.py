"""MinIO wrapper. The WORM archive is content-addressed and write-once (ADR-0002 decision 6)."""

from __future__ import annotations

from functools import lru_cache

from minio import Minio

from regops_shared.settings import get_settings

#: Canonical buckets, each prefixed with ``minio_bucket_prefix``.
BUCKETS = ("archive", "exports", "evidence")


@lru_cache
def get_minio() -> Minio:
    settings = get_settings()
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def bucket_name(logical: str) -> str:
    return f"{get_settings().minio_bucket_prefix}{logical}"


def ensure_buckets() -> None:
    client = get_minio()
    for logical in BUCKETS:
        name = bucket_name(logical)
        if not client.bucket_exists(name):
            client.make_bucket(name)


__all__ = ["BUCKETS", "bucket_name", "ensure_buckets", "get_minio"]
