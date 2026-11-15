"""Lago de datos: la misma interfaz para una carpeta local o un bucket compatible con S3.

En el Mac se usa `DATA_URI=data`; con MinIO o con OCI Object Storage, `DATA_URI=s3://bucket`.
Las claves siguen las capas del lago: bronze/, silver/, models/, monitoring/.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import Settings, get_settings


class Storage:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        if self.settings.is_s3:
            self.bucket = self.settings.data_uri.removeprefix("s3://").strip("/")
            self._client = _s3_client(self.settings)
            self.root = None
        else:
            self.root = Path(self.settings.data_uri)
            self._client = None

    # --- bytes -------------------------------------------------------------------------
    def write_bytes(self, key: str, data: bytes) -> None:
        if self._client:
            self._client.put_object(Bucket=self.bucket, Key=key, Body=data)
        else:
            path = self.root / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def read_bytes(self, key: str) -> bytes:
        if self._client:
            return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return (self.root / key).read_bytes()

    def exists(self, key: str) -> bool:
        if self._client:
            from botocore.exceptions import ClientError

            try:
                self._client.head_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError:
                return False
        return (self.root / key).exists()

    def list(self, prefix: str) -> list[str]:
        if self._client:
            keys: list[str] = []
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                keys += [obj["Key"] for obj in page.get("Contents", [])]
            return sorted(keys)
        base = self.root / prefix
        if not base.exists():
            return []
        if base.is_file():
            return [prefix]
        return sorted(str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file())

    # --- formatos ----------------------------------------------------------------------
    def write_parquet(self, df: pd.DataFrame, key: str) -> None:
        buffer = io.BytesIO()
        df.to_parquet(buffer, index=False)
        self.write_bytes(key, buffer.getvalue())

    def read_parquet(self, key: str) -> pd.DataFrame:
        return pd.read_parquet(io.BytesIO(self.read_bytes(key)))

    def read_parquet_or_empty(self, key: str) -> pd.DataFrame:
        return self.read_parquet(key) if self.exists(key) else pd.DataFrame()

    def append_parquet(self, df: pd.DataFrame, key: str, dedupe_on: list[str] | None = None):
        """Agrega filas a una tabla pequeña (historial de métricas). Reemplaza duplicados."""
        old = self.read_parquet_or_empty(key)
        merged = pd.concat([old, df], ignore_index=True) if len(old) else df
        if dedupe_on:
            merged = merged.drop_duplicates(subset=dedupe_on, keep="last")
        self.write_parquet(merged.reset_index(drop=True), key)
        return merged

    def write_json(self, obj: Any, key: str) -> None:
        text = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
        self.write_bytes(key, text.encode("utf-8"))

    def read_json(self, key: str, default: Any = None) -> Any:
        if not self.exists(key):
            return default
        return json.loads(self.read_bytes(key).decode("utf-8"))


def _s3_client(settings: Settings):
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key_id or None,
        aws_secret_access_key=settings.s3_secret_access_key or None,
        region_name=settings.s3_region,
        # OCI Object Storage pide estilo "path" y no acepta los checksums nuevos de boto3.
        config=Config(
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
