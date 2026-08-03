"""MinIO wrapper and the WORM archive.

The archive is **content-addressed and write-once** (ADR-0002 decision 6). Two properties follow
from that and both are relied on downstream:

- The key *is* the hash, so an identical fetch resolves to the object already there. There is no
  overwrite path — :func:`archive_bytes` returns the existing key rather than re-uploading, and
  never mutates an object.
- What is archived is the **raw response, unmodified**. Canonicalization exists for change
  detection only; it never touches what gets stored or cited.

Do not confuse the two hashes:

===================  ==========================================  ==========================
``raw_object_key``   ``sha256(raw response bytes)``              the WORM key — what is cited
``content_hash``     ``sha256(canonicalized body)``              what change detection keys on
===================  ==========================================  ==========================
"""

from __future__ import annotations

import hashlib
import io
from functools import lru_cache
from typing import Final

from minio import Minio
from minio.error import S3Error

from regops_shared.settings import get_settings

#: Canonical buckets, each prefixed with ``minio_bucket_prefix``.
BUCKETS = ("archive", "exports", "evidence")

#: Objects are sharded by the first two hex characters of the digest — a flat bucket with a
#: six-figure object count is unpleasant to browse and slow to list.
ARCHIVE_BUCKET: Final[str] = "archive"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


class CredentialInArchiveError(RuntimeError):
    """A payload carrying a source credential was offered to the write-once archive.

    Raised rather than redacted: the archive stores the raw response **unmodified**, so there is no
    version of this that both keeps the evidence intact and keeps the key out. Refusing is the only
    correct answer, and it must happen before the write because the archive is immutable — a
    credential that lands here can never be removed.

    This is a live hazard, not a theoretical one. 국가법령정보's 목록 endpoints echo the ``OC``
    parameter back inside the response body (``행정규칙상세링크`` is a fully-formed URL containing
    it), so "we never log the resolved URL" is not sufficient on its own.
    """


def _assert_no_credential(data: bytes) -> None:
    for secret in get_settings().source_credentials:
        if secret.encode("utf-8") in data:
            raise CredentialInArchiveError(
                "response body contains a configured source credential — refusing to archive. "
                "Some authority endpoints echo the key back in the payload; that response must be "
                "consumed in memory, never written to the immutable archive."
            )


def object_key(digest: str) -> str:
    """``sha256/ab/abcdef…`` — the key is derived from the content and from nothing else."""
    return f"sha256/{digest[:2]}/{digest}"


def archive_bytes(data: bytes, *, content_type: str | None = None) -> tuple[str, str]:
    """Write ``data`` to the WORM archive and return ``(raw_object_key, digest)``.

    Idempotent by construction: the key is the digest, so re-archiving identical bytes is a no-op
    that returns the existing key. An object that already exists is **never** overwritten — if the
    key is present, the bytes behind it are by definition the same bytes.

    Refuses any payload containing a configured source credential
    (:class:`CredentialInArchiveError`). The check lives here rather than at the call site so that
    no future caller can forget it.
    """
    _assert_no_credential(data)
    digest = sha256_hex(data)
    key = object_key(digest)
    client = get_minio()
    bucket = bucket_name(ARCHIVE_BUCKET)

    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    try:
        client.stat_object(bucket, key)
        return key, digest  # already archived — write-once means we stop here
    except S3Error as exc:
        if exc.code not in {"NoSuchKey", "NoSuchObject", "NotFound"}:
            raise

    client.put_object(
        bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type or "application/octet-stream",
    )
    return key, digest


def read_archived(raw_object_key: str) -> bytes:
    """Read an archived object back.

    Everything downstream reads from here, never from the network.
    """
    response = get_minio().get_object(bucket_name(ARCHIVE_BUCKET), raw_object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


__all__ = [
    "ARCHIVE_BUCKET",
    "BUCKETS",
    "CredentialInArchiveError",
    "archive_bytes",
    "bucket_name",
    "ensure_buckets",
    "get_minio",
    "object_key",
    "read_archived",
    "sha256_hex",
]
