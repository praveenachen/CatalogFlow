from __future__ import annotations

import hashlib
import os
import re
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class StorageConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class StoredObject:
    uri: str
    key: str
    checksum: str
    batch_id: int
    merchant_id: int | None
    uploaded_at: datetime
    size_bytes: int


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _segment(value: int | str | None, fallback: str) -> str:
    text = str(value) if value is not None else fallback
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", text)
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("Invalid storage path segment.")
    return cleaned


class CatalogStorage(ABC):
    @abstractmethod
    def save_raw(self, payload: bytes, batch_id: int, merchant_id: int | None, filename: str) -> StoredObject:
        raise NotImplementedError

    @abstractmethod
    def save_processed(self, payload: bytes, batch_id: int, merchant_id: int | None, filename: str = "silver.jsonl") -> StoredObject:
        raise NotImplementedError

    @abstractmethod
    def save_curated(self, payload: bytes, batch_id: int, merchant_id: int | None, filename: str = "gold.jsonl") -> StoredObject:
        raise NotImplementedError

    @abstractmethod
    def save_report(self, payload: bytes, batch_id: int, merchant_id: int | None, filename: str = "batch_quality_metrics.json") -> StoredObject:
        raise NotImplementedError

    @abstractmethod
    def read(self, uri: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def exists(self, uri: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def location(self, layer: str, batch_id: int, merchant_id: int | None, filename: str) -> str:
        raise NotImplementedError


class LocalCatalogStorage(CatalogStorage):
    def __init__(self, root: str | Path = ".catalogflow-data") -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, layer: str, batch_id: int, merchant_id: int | None, filename: str) -> Path:
        path = self.root / _segment(layer, "data") / _segment(merchant_id, "default") / _segment(batch_id, "batch") / _segment(filename, "data")
        resolved = path.resolve()
        if self.root not in resolved.parents:
            raise ValueError("Storage path escapes the configured root.")
        return resolved

    def _save(
        self,
        layer: str,
        payload: bytes,
        batch_id: int,
        merchant_id: int | None,
        filename: str,
        immutable: bool,
    ) -> StoredObject:
        path = self._path(layer, batch_id, merchant_id, filename)
        checksum = sha256_bytes(payload)
        if path.exists() and immutable:
            if sha256_bytes(path.read_bytes()) != checksum:
                raise FileExistsError(f"Immutable raw object already exists: {path.name}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return StoredObject(path.as_uri(), str(path.relative_to(self.root)).replace("\\", "/"), checksum, batch_id, merchant_id, datetime.now(timezone.utc), len(payload))

    def save_raw(self, payload: bytes, batch_id: int, merchant_id: int | None, filename: str) -> StoredObject:
        return self._save("raw", payload, batch_id, merchant_id, "source.csv", immutable=True)

    def save_processed(self, payload: bytes, batch_id: int, merchant_id: int | None, filename: str = "silver.jsonl") -> StoredObject:
        return self._save("processed", payload, batch_id, merchant_id, filename, immutable=False)

    def save_curated(self, payload: bytes, batch_id: int, merchant_id: int | None, filename: str = "gold.jsonl") -> StoredObject:
        return self._save("curated", payload, batch_id, merchant_id, filename, immutable=False)

    def save_report(self, payload: bytes, batch_id: int, merchant_id: int | None, filename: str = "batch_quality_metrics.json") -> StoredObject:
        return self._save("reports", payload, batch_id, merchant_id, filename, immutable=False)

    def read(self, uri: str) -> bytes:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            raise ValueError("Local storage can only read file:// URIs.")
        path = Path(parsed.path.lstrip("/") if os.name == "nt" else parsed.path).resolve()
        if self.root not in path.parents:
            raise ValueError("URI is outside the configured storage root.")
        return path.read_bytes()

    def exists(self, uri: str) -> bool:
        try:
            parsed = urlparse(uri)
            path = Path(parsed.path.lstrip("/") if os.name == "nt" else parsed.path).resolve()
            return parsed.scheme == "file" and self.root in path.parents and path.is_file()
        except (OSError, ValueError):
            return False

    def location(self, layer: str, batch_id: int, merchant_id: int | None, filename: str) -> str:
        return self._path(layer, batch_id, merchant_id, filename).as_uri()


class S3CatalogStorage(CatalogStorage):
    def __init__(self, bucket: str, region: str | None = None, client: Any | None = None) -> None:
        if not bucket:
            raise StorageConfigurationError("AWS_S3_BUCKET is required for S3 storage.")
        if client is None:
            import boto3

            client = boto3.client("s3", region_name=region)
        self.bucket = bucket
        self.client = client

    def _key(self, layer: str, batch_id: int, merchant_id: int | None, filename: str) -> str:
        return "/".join((_segment(layer, "data"), _segment(merchant_id, "default"), _segment(batch_id, "batch"), _segment(filename, "data")))

    def _save(self, layer: str, payload: bytes, batch_id: int, merchant_id: int | None, filename: str, immutable: bool) -> StoredObject:
        key = self._key(layer, batch_id, merchant_id, filename)
        uri = f"s3://{self.bucket}/{key}"
        checksum = sha256_bytes(payload)
        arguments = dict(
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType="text/csv" if filename.endswith(".csv") else "application/x-ndjson",
            ServerSideEncryption="AES256",
            Metadata={"sha256": checksum, "batch-id": str(batch_id), "merchant-id": str(merchant_id or "default")},
        )
        if immutable:
            arguments["IfNoneMatch"] = "*"
        try:
            self.client.put_object(**arguments)
        except self.client.exceptions.ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if immutable and code in {"409", "412", "ConditionalRequestConflict", "PreconditionFailed"}:
                raise FileExistsError(f"Immutable raw object already exists: {key}") from exc
            raise
        return StoredObject(uri, key, checksum, batch_id, merchant_id, datetime.now(timezone.utc), len(payload))

    def save_raw(self, payload: bytes, batch_id: int, merchant_id: int | None, filename: str) -> StoredObject:
        return self._save("raw", payload, batch_id, merchant_id, "source.csv", immutable=True)

    def save_processed(self, payload: bytes, batch_id: int, merchant_id: int | None, filename: str = "silver.jsonl") -> StoredObject:
        return self._save("processed", payload, batch_id, merchant_id, filename, immutable=False)

    def save_curated(self, payload: bytes, batch_id: int, merchant_id: int | None, filename: str = "gold.jsonl") -> StoredObject:
        return self._save("curated", payload, batch_id, merchant_id, filename, immutable=False)

    def save_report(self, payload: bytes, batch_id: int, merchant_id: int | None, filename: str = "batch_quality_metrics.json") -> StoredObject:
        return self._save("reports", payload, batch_id, merchant_id, filename, immutable=False)

    def read(self, uri: str) -> bytes:
        bucket, key = self._parse_uri(uri)
        return self.client.get_object(Bucket=bucket, Key=key)["Body"].read()

    def exists(self, uri: str) -> bool:
        bucket, key = self._parse_uri(uri)
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except self.client.exceptions.ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def _parse_uri(self, uri: str) -> tuple[str, str]:
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or parsed.netloc != self.bucket:
            raise ValueError("S3 URI does not belong to the configured bucket.")
        return parsed.netloc, parsed.path.lstrip("/")

    def location(self, layer: str, batch_id: int, merchant_id: int | None, filename: str) -> str:
        return f"s3://{self.bucket}/{self._key(layer, batch_id, merchant_id, filename)}"
