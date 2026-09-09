"""S3-compatible durable storage for user-visible artifacts."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.config import (
    OBJECT_STORAGE_ACCESS_KEY_ID, OBJECT_STORAGE_BUCKET, OBJECT_STORAGE_ENDPOINT_URL,
    OBJECT_STORAGE_FORCE_PATH_STYLE, OBJECT_STORAGE_PREFIX, OBJECT_STORAGE_PRESIGN_SECONDS,
    OBJECT_STORAGE_REGION, OBJECT_STORAGE_SECRET_ACCESS_KEY,
    OBJECT_STORAGE_OUTPUT_RETENTION_DAYS, OBJECT_STORAGE_SUPPORT_RETENTION_DAYS,
)


class ObjectStorageUnavailable(RuntimeError):
    pass


def enabled() -> bool:
    return bool(OBJECT_STORAGE_BUCKET)


def key(name: str) -> str:
    normalized = name.strip().lstrip("/")
    if not normalized or ".." in normalized.split("/") or "\\" in normalized:
        raise ValueError("Object storage key must be a safe relative path.")
    return f"{OBJECT_STORAGE_PREFIX}/{normalized}" if OBJECT_STORAGE_PREFIX else normalized


@lru_cache(maxsize=1)
def client():
    if not enabled():
        raise ObjectStorageUnavailable("OBJECT_STORAGE_BUCKET is not configured.")
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:  # pragma: no cover
        raise ObjectStorageUnavailable("boto3 must be installed for object storage.") from exc
    options: dict[str, Any] = {
        "service_name": "s3", "region_name": OBJECT_STORAGE_REGION,
        "endpoint_url": OBJECT_STORAGE_ENDPOINT_URL or None,
        "config": Config(s3={"addressing_style": "path" if OBJECT_STORAGE_FORCE_PATH_STYLE else "auto"}),
    }
    if OBJECT_STORAGE_ACCESS_KEY_ID:
        options["aws_access_key_id"] = OBJECT_STORAGE_ACCESS_KEY_ID
    if OBJECT_STORAGE_SECRET_ACCESS_KEY:
        options["aws_secret_access_key"] = OBJECT_STORAGE_SECRET_ACCESS_KEY
    return boto3.client(**options)


def upload_file(local_path: Path, object_name: str, *, content_type: str | None = None) -> str:
    object_key = key(object_name)
    try:
        client().upload_file(str(local_path), OBJECT_STORAGE_BUCKET, object_key, ExtraArgs={"ContentType": content_type} if content_type else None)
    except Exception as exc:  # noqa: BLE001
        raise ObjectStorageUnavailable(f"Could not upload object {object_key!r}.") from exc
    return object_key


def put_bytes(value: bytes, object_name: str, *, content_type: str) -> str:
    object_key = key(object_name)
    try:
        client().put_object(Bucket=OBJECT_STORAGE_BUCKET, Key=object_key, Body=value, ContentType=content_type)
    except Exception as exc:  # noqa: BLE001
        raise ObjectStorageUnavailable(f"Could not write object {object_key!r}.") from exc
    return object_key


def get_bytes(object_name: str) -> bytes | None:
    object_key = key(object_name)
    try:
        response = client().get_object(Bucket=OBJECT_STORAGE_BUCKET, Key=object_key)
        return response["Body"].read()
    except Exception as exc:  # noqa: BLE001
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise ObjectStorageUnavailable(f"Could not read object {object_key!r}.") from exc


def delete_object(object_name: str) -> None:
    object_key = key(object_name)
    try:
        client().delete_object(Bucket=OBJECT_STORAGE_BUCKET, Key=object_key)
    except Exception as exc:  # noqa: BLE001
        raise ObjectStorageUnavailable(f"Could not delete object {object_key!r}.") from exc


def exists(object_name: str) -> bool:
    object_key = key(object_name)
    try:
        client().head_object(Bucket=OBJECT_STORAGE_BUCKET, Key=object_key)
    except Exception as exc:  # noqa: BLE001
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise ObjectStorageUnavailable(f"Could not check object {object_key!r}.") from exc
    return True


def presigned_download_url(object_name: str, *, download_name: str) -> str:
    object_key = key(object_name)
    try:
        return client().generate_presigned_url("get_object", Params={"Bucket": OBJECT_STORAGE_BUCKET, "Key": object_key, "ResponseContentDisposition": f'attachment; filename="{download_name}"'}, ExpiresIn=OBJECT_STORAGE_PRESIGN_SECONDS)
    except Exception as exc:  # noqa: BLE001
        raise ObjectStorageUnavailable(f"Could not create download URL for {object_key!r}.") from exc


def status() -> str:
    if not enabled():
        return "not_configured"
    try:
        client().head_bucket(Bucket=OBJECT_STORAGE_BUCKET)
    except Exception:
        return "unavailable"
    return "ok"


def _lifecycle_rule_id(name: str) -> str:
    prefix = OBJECT_STORAGE_PREFIX or "root"
    return f"esm-scm-{prefix.replace('/', '-')}-{name}-retention"


def lifecycle_rules() -> list[dict[str, object]]:
    """The two managed rules, intentionally limited to our prefix only."""
    managed_prefix = f"{OBJECT_STORAGE_PREFIX}/" if OBJECT_STORAGE_PREFIX else ""
    return [
        {
            "ID": _lifecycle_rule_id("outputs"),
            "Status": "Enabled",
            "Filter": {"Prefix": f"{managed_prefix}outputs/"},
            "Expiration": {"Days": OBJECT_STORAGE_OUTPUT_RETENTION_DAYS},
            "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
        },
        {
            "ID": _lifecycle_rule_id("support"),
            "Status": "Enabled",
            "Filter": {"Prefix": f"{managed_prefix}support/"},
            "Expiration": {"Days": OBJECT_STORAGE_SUPPORT_RETENTION_DAYS},
            "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
        },
    ]


def lifecycle_status() -> str:
    if not enabled():
        return "not_configured"
    expected_ids = {str(rule["ID"]) for rule in lifecycle_rules()}
    try:
        configured = client().get_bucket_lifecycle_configuration(Bucket=OBJECT_STORAGE_BUCKET)
        configured_ids = {str(rule.get("ID")) for rule in configured.get("Rules", [])}
    except Exception as exc:  # noqa: BLE001
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"NoSuchLifecycleConfiguration", "NoSuchLifecycle", "404", "NotFound"}:
            return "missing"
        return "unavailable"
    return "ok" if expected_ids <= configured_ids else "missing"


def apply_lifecycle_rules() -> dict[str, object]:
    """Merge managed rules without replacing unrelated bucket lifecycle rules."""
    if not enabled():
        raise ObjectStorageUnavailable("OBJECT_STORAGE_BUCKET is not configured.")
    desired_rules = lifecycle_rules()
    managed_ids = {str(rule["ID"]) for rule in desired_rules}
    try:
        current = client().get_bucket_lifecycle_configuration(Bucket=OBJECT_STORAGE_BUCKET)
        existing_rules = list(current.get("Rules", []))
    except Exception as exc:  # noqa: BLE001
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"NoSuchLifecycleConfiguration", "NoSuchLifecycle", "404", "NotFound"}:
            existing_rules = []
        else:
            raise ObjectStorageUnavailable("Could not read bucket lifecycle configuration.") from exc
    preserved_rules = [rule for rule in existing_rules if str(rule.get("ID")) not in managed_ids]
    merged_rules = [*preserved_rules, *desired_rules]
    try:
        client().put_bucket_lifecycle_configuration(
            Bucket=OBJECT_STORAGE_BUCKET,
            LifecycleConfiguration={"Rules": merged_rules},
        )
    except Exception as exc:  # noqa: BLE001
        raise ObjectStorageUnavailable("Could not apply bucket lifecycle configuration.") from exc
    return {"bucket": OBJECT_STORAGE_BUCKET, "rules": desired_rules, "preserved_rule_count": len(preserved_rules)}
