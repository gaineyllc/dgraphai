"""
Google Cloud Storage connector.
Config: {bucket, prefix, credentials_json or use_adc}
Supports Application Default Credentials (for GKE) or service account JSON.
"""
from __future__ import annotations
from pathlib import PurePosixPath
from typing import AsyncIterator
from .sdk import BaseConnector, ConnectorFileRecord, ConnectorManifest


class GCSConnector(BaseConnector):
    manifest = ConnectorManifest(
        id          = "gcs",
        name        = "Google Cloud Storage",
        description = "Index objects from a GCS bucket",
        version     = "1.0.0",
        author      = "dgraph.ai",
        icon_url    = "https://dgraph.ai/icons/gcs.svg",
        config_schema = {
            "type": "object",
            "properties": {
                "bucket":           {"type": "string", "title": "Bucket name"},
                "prefix":           {"type": "string", "title": "Object prefix (optional)", "default": ""},
                "use_adc":          {"type": "boolean", "title": "Use Application Default Credentials", "default": True,
                                     "description": "Recommended for GKE/Cloud Run. Uncheck to use service account JSON."},
                "credentials_json": {"type": "string", "title": "Service account JSON key",
                                     "format": "password",
                                     "description": "Paste the full service account JSON. Only needed if ADC is off."},
                "project_id":       {"type": "string", "title": "GCP Project ID (optional)"},
            },
            "required": ["bucket"],
        },
        capabilities = ["read", "stream"],
    )

    def _get_client(self):
        try:
            from google.cloud import storage
            from google.oauth2 import service_account
        except ImportError:
            raise RuntimeError("google-cloud-storage required: uv add google-cloud-storage")

        use_adc = self.config.get("use_adc", True)
        if use_adc:
            return storage.Client(project=self.config.get("project_id"))

        creds_json = self.config.get("credentials_json", "")
        if not creds_json:
            raise ValueError("credentials_json required when use_adc is false")

        import json
        creds_info = json.loads(creds_json) if isinstance(creds_json, str) else creds_json
        creds = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return storage.Client(credentials=creds, project=self.config.get("project_id"))

    async def walk(self) -> AsyncIterator[ConnectorFileRecord]:
        import asyncio
        client = self._get_client()
        bucket = self.config["bucket"]
        prefix = self.config.get("prefix", "")

        # GCS client is sync — run in thread pool
        loop = asyncio.get_event_loop()
        blobs = await loop.run_in_executor(
            None,
            lambda: list(client.list_blobs(bucket, prefix=prefix))
        )

        for blob in blobs:
            if blob.name.endswith("/"):
                continue
            yield ConnectorFileRecord(
                path       = f"gs://{bucket}/{blob.name}",
                name       = blob.name.split("/")[-1],
                size_bytes = blob.size or 0,
                modified   = blob.updated.timestamp() if blob.updated else 0.0,
                suffix     = PurePosixPath(blob.name).suffix.lower(),
                bucket     = bucket,
                key        = blob.name,
                etag       = blob.etag or "",
                extra      = {
                    "content_type":     blob.content_type or "",
                    "storage_class":    blob.storage_class or "",
                    "public_url":       blob.public_url,
                    "generation":       str(blob.generation),
                },
            )

    async def test_connection(self):
        try:
            client = self._get_client()
            bucket = client.bucket(self.config["bucket"])
            bucket.reload()
            return {"success": True, "message": f"Connected to gs://{self.config['bucket']}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
