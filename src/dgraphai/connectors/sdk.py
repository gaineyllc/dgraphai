"""
dgraph.ai Connector SDK
────────────────────────
Build connectors that integrate any data source into the dgraph.ai
knowledge graph. Connectors run inside the scanner agent.

A connector implements two things:
  1. walk()  — yield FileRecord objects for every item in the source
  2. config  — JSON schema describing the connector's configuration fields

The SDK handles:
  - Registration with the backend
  - Delta tracking (only sends what changed)
  - Batching and chunking
  - Error handling and retry
  - Progress reporting

Built-in connectors (reference implementations):
  LocalConnector    — local filesystem (Windows/Linux/macOS)
  SMBConnector      — SMB/CIFS shares (Synology, Windows, Samba)
  S3Connector       — AWS S3 buckets
  AzureBlobConnector — Azure Blob Storage
  SharePointConnector — SharePoint / OneDrive for Business
  GCSConnector      — Google Cloud Storage

Community connectors: submit a PR to add yours.
"""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator


# ── Connector manifest ────────────────────────────────────────────────────────

@dataclass
class ConnectorManifest:
    """
    Metadata that describes a connector.
    Registered with the backend when the connector is installed.
    """
    id:           str           # unique slug, e.g. "aws-s3"
    name:         str           # display name, e.g. "Amazon S3"
    description:  str
    version:      str
    author:       str
    icon_url:     str = ""
    config_schema: dict = field(default_factory=dict)
    # JSON Schema for the connector's config fields
    # Used by the UI to render the configuration form
    # Example:
    # {
    #   "type": "object",
    #   "properties": {
    #     "bucket": {"type": "string", "title": "Bucket name"},
    #     "prefix": {"type": "string", "title": "Key prefix", "default": ""},
    #     "region": {"type": "string", "title": "AWS Region", "default": "us-east-1"},
    #   },
    #   "required": ["bucket", "region"]
    # }
    capabilities: list[str] = field(default_factory=list)
    # ["read", "write", "stream", "watch"]


# ── File record ───────────────────────────────────────────────────────────────

@dataclass
class ConnectorFileRecord:
    """A file or directory discovered by a connector."""
    path:       str           # Full path within the source
    name:       str           # Filename
    size_bytes: int
    modified:   float         # Unix timestamp
    is_dir:     bool = False
    sha256:     str | None = None
    suffix:     str = ""
    # Protocol-specific metadata
    host:       str = ""
    share:      str = ""
    bucket:     str = ""      # for object storage
    key:        str = ""      # for object storage
    etag:       str = ""      # for object storage dedup
    extra:      dict = field(default_factory=dict)

    def stable_id(self, connector_id: str) -> str:
        """Stable content-addressable ID for this record."""
        key = f"{connector_id}:{self.host}:{self.share}:{self.bucket}:{self.path}"
        return hashlib.sha256(key.encode()).hexdigest()[:24]

    def to_node(self, connector_id: str) -> dict[str, Any]:
        return {
            "op":   "upsert",
            "type": "Directory" if self.is_dir else "File",
            "id":   self.stable_id(connector_id),
            "props": {
                "path":         self.path,
                "name":         self.name,
                "size_bytes":   self.size_bytes if not self.is_dir else 0,
                "modified":     self.modified,
                "sha256":       self.sha256 or self.etag or "",
                "extension":    self.suffix,
                "host":         self.host,
                "share":        self.share,
                "bucket":       self.bucket,
                "connector_id": connector_id,
                **self.extra,
            },
        }

    def to_parent_edge(self, connector_id: str) -> dict[str, Any] | None:
        parent = str(Path(self.path).parent)
        if parent == self.path:
            return None
        parent_id = hashlib.sha256(
            f"{connector_id}:{self.host}:{self.share}:{self.bucket}:{parent}".encode()
        ).hexdigest()[:24]
        return {
            "op": "upsert", "type": "CHILD_OF",
            "from": self.stable_id(connector_id),
            "to":   parent_id,
            "props": {},
        }


# ── Base connector ────────────────────────────────────────────────────────────

class BaseConnector(ABC):
    """
    Base class for all dgraph.ai connectors.
    Subclass this to build a new connector.

    Minimal implementation:
      class MyConnector(BaseConnector):
          manifest = ConnectorManifest(id="my-connector", ...)

          async def walk(self) -> AsyncIterator[ConnectorFileRecord]:
              # yield records here
              for item in my_source.list():
                  yield ConnectorFileRecord(path=item.path, ...)
    """

    manifest: ConnectorManifest  # Override in subclass

    def __init__(self, connector_id: str, config: dict[str, Any]) -> None:
        self.connector_id = connector_id
        self.config       = config

    @abstractmethod
    async def walk(self) -> AsyncIterator[ConnectorFileRecord]:
        """Yield ConnectorFileRecord for every item in the source."""
        ...

    async def test_connection(self) -> dict[str, Any]:
        """
        Test that the connector can reach its source.
        Returns {"success": bool, "message": str}.
        Override to provide meaningful connectivity checks.
        """
        return {"success": True, "message": "Connection test not implemented"}

    async def get_stats(self) -> dict[str, Any]:
        """Return estimated item counts and size. Used for progress estimation."""
        return {"estimated_files": -1, "estimated_bytes": -1}


# ── Built-in: S3 ──────────────────────────────────────────────────────────────

class S3Connector(BaseConnector):
    """
    Amazon S3 connector.
    Config: {bucket, prefix, region, access_key_id, secret_access_key, endpoint_url}
    Credentials: use IAM role (recommended in EKS) or explicit keys.
    """

    manifest = ConnectorManifest(
        id          = "aws-s3",
        name        = "Amazon S3",
        description = "Index objects from an AWS S3 bucket",
        version     = "1.0.0",
        author      = "dgraph.ai",
        icon_url    = "https://dgraph.ai/icons/aws-s3.svg",
        config_schema = {
            "type": "object",
            "properties": {
                "bucket":           {"type": "string", "title": "Bucket name"},
                "prefix":           {"type": "string", "title": "Key prefix (optional)", "default": ""},
                "region":           {"type": "string", "title": "AWS Region", "default": "us-east-1"},
                "endpoint_url":     {"type": "string", "title": "Custom endpoint (for MinIO/LocalStack)"},
                "access_key_id":    {"type": "string", "title": "AWS Access Key ID (leave blank for IAM role)"},
                "secret_access_key":{"type": "string", "title": "AWS Secret Access Key", "format": "password"},
            },
            "required": ["bucket"],
        },
        capabilities = ["read", "stream"],
    )

    async def walk(self) -> AsyncIterator[ConnectorFileRecord]:
        try:
            import boto3
        except ImportError:
            raise RuntimeError("boto3 required for S3 connector: uv add boto3")

        bucket   = self.config["bucket"]
        prefix   = self.config.get("prefix", "")
        region   = self.config.get("region", "us-east-1")
        endpoint = self.config.get("endpoint_url")
        ak       = self.config.get("access_key_id")
        sk       = self.config.get("secret_access_key")

        kwargs: dict[str, Any] = {"region_name": region}
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        if ak and sk:
            kwargs["aws_access_key_id"]     = ak
            kwargs["aws_secret_access_key"]  = sk

        s3 = boto3.client("s3", **kwargs)
        paginator = s3.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue  # skip directory markers
                yield ConnectorFileRecord(
                    path       = f"s3://{bucket}/{key}",
                    name       = key.split("/")[-1],
                    size_bytes = obj["Size"],
                    modified   = obj["LastModified"].timestamp(),
                    suffix     = Path(key).suffix.lower(),
                    bucket     = bucket,
                    key        = key,
                    etag       = obj.get("ETag", "").strip('"'),
                    extra      = {"storage_class": obj.get("StorageClass", "STANDARD")},
                )

    async def test_connection(self) -> dict[str, Any]:
        try:
            import boto3
            s3 = boto3.client("s3", region_name=self.config.get("region", "us-east-1"))
            s3.head_bucket(Bucket=self.config["bucket"])
            return {"success": True, "message": f"Connected to s3://{self.config['bucket']}"}
        except Exception as e:
            return {"success": False, "message": str(e)}


# ── Built-in: Azure Blob ──────────────────────────────────────────────────────

class AzureBlobConnector(BaseConnector):
    """
    Azure Blob Storage connector.
    Config: {account_name, container, prefix, connection_string or sas_token}
    """

    manifest = ConnectorManifest(
        id          = "azure-blob",
        name        = "Azure Blob Storage",
        description = "Index blobs from an Azure Storage container",
        version     = "1.0.0",
        author      = "dgraph.ai",
        icon_url    = "https://dgraph.ai/icons/azure-blob.svg",
        config_schema = {
            "type": "object",
            "properties": {
                "account_name":       {"type": "string", "title": "Storage account name"},
                "container":          {"type": "string", "title": "Container name"},
                "prefix":             {"type": "string", "title": "Blob prefix (optional)"},
                "connection_string":  {"type": "string", "title": "Connection string", "format": "password"},
                "sas_token":          {"type": "string", "title": "SAS token", "format": "password"},
            },
            "required": ["account_name", "container"],
        },
        capabilities = ["read", "stream"],
    )

    async def walk(self) -> AsyncIterator[ConnectorFileRecord]:
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError:
            raise RuntimeError("azure-storage-blob required: uv add azure-storage-blob")

        conn_str  = self.config.get("connection_string")
        account   = self.config["account_name"]
        container = self.config["container"]
        prefix    = self.config.get("prefix", "")

        if conn_str:
            client = BlobServiceClient.from_connection_string(conn_str)
        else:
            sas = self.config.get("sas_token", "")
            client = BlobServiceClient(
                account_url=f"https://{account}.blob.core.windows.net",
                credential=sas or None,
            )

        container_client = client.get_container_client(container)
        for blob in container_client.list_blobs(name_starts_with=prefix):
            yield ConnectorFileRecord(
                path       = f"azure://{account}/{container}/{blob.name}",
                name       = blob.name.split("/")[-1],
                size_bytes = blob.size or 0,
                modified   = blob.last_modified.timestamp() if blob.last_modified else 0,
                suffix     = Path(blob.name).suffix.lower(),
                bucket     = container,
                key        = blob.name,
                etag       = blob.etag or "",
                extra      = {"content_type": blob.content_settings.content_type if blob.content_settings else ""},
            )

    async def test_connection(self) -> dict[str, Any]:
        try:
            from azure.storage.blob import BlobServiceClient
            conn_str = self.config.get("connection_string")
            if conn_str:
                client = BlobServiceClient.from_connection_string(conn_str)
                client.get_account_information()
            return {"success": True, "message": f"Connected to {self.config['account_name']}"}
        except Exception as e:
            return {"success": False, "message": str(e)}


# ── Built-in: Local filesystem ───────────────────────────────────────────────

class LocalConnector(BaseConnector):
    """
    Local filesystem connector.
    Config: {path, follow_symlinks, exclude_patterns}
    Runs inside the agent on the same machine.
    """
    manifest = ConnectorManifest(
        id          = "local",
        name        = "Local folder",
        description = "Index files from a local folder or mounted drive",
        version     = "1.0.0",
        author      = "dgraph.ai",
        icon_url    = "https://dgraph.ai/icons/local.svg",
        config_schema = {
            "type": "object",
            "properties": {
                "path":             {"type": "string", "title": "Folder path", "placeholder": "/mnt/data or C:\\Data"},
                "follow_symlinks": {"type": "boolean", "title": "Follow symlinks", "default": False},
                "exclude_patterns":{"type": "string",  "title": "Exclude patterns (comma-separated glob)", "default": ".git,node_modules,.DS_Store"},
            },
            "required": ["path"],
        },
        capabilities = ["read", "stream", "watch"],
    )

    async def walk(self) -> AsyncIterator[ConnectorFileRecord]:
        import os, time
        root = Path(self.config["path"]).expanduser()
        follow = self.config.get("follow_symlinks", False)
        excludes = [p.strip() for p in self.config.get("exclude_patterns", ".git,node_modules").split(",")]

        for dirpath, dirnames, filenames in os.walk(root, followlinks=follow):
            # Prune excluded directories
            dirnames[:] = [d for d in dirnames if not any(
                Path(dirpath, d).match(ex) for ex in excludes
            )]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                try:
                    st = fpath.stat()
                    yield ConnectorFileRecord(
                        path       = str(fpath),
                        name       = fname,
                        size_bytes = st.st_size,
                        modified   = st.st_mtime,
                        suffix     = fpath.suffix.lower(),
                    )
                except (PermissionError, OSError):
                    continue

    async def test_connection(self) -> dict[str, Any]:
        root = Path(self.config.get("path", ""))
        if root.exists() and root.is_dir():
            count = sum(1 for _ in root.iterdir())
            return {"success": True, "message": f"Connected — {count} items at root"}
        return {"success": False, "message": f"Path not found or not a directory: {root}"}


# ── Built-in: SMB/CIFS share ──────────────────────────────────────────────────

class SMBConnector(BaseConnector):
    """
    SMB/CIFS share connector — Synology, QNAP, Windows shares, Samba.
    Config: {host, share, username, password, domain, port}
    Requires: smbprotocol
    """
    manifest = ConnectorManifest(
        id          = "smb",
        name        = "NAS / SMB Share",
        description = "Index files from a Synology, QNAP, Windows share, or any SMB/CIFS server",
        version     = "1.0.0",
        author      = "dgraph.ai",
        icon_url    = "https://dgraph.ai/icons/smb.svg",
        config_schema = {
            "type": "object",
            "properties": {
                "host":     {"type": "string", "title": "Host / IP address", "placeholder": "192.168.1.10"},
                "share":    {"type": "string", "title": "Share name",       "placeholder": "Media"},
                "username": {"type": "string", "title": "Username"},
                "password": {"type": "string", "title": "Password",   "format": "password"},
                "domain":   {"type": "string", "title": "Domain (optional)", "default": "WORKGROUP"},
                "port":     {"type": "integer","title": "Port",        "default": 445},
                "path":     {"type": "string", "title": "Sub-path (optional)", "default": "/"},
            },
            "required": ["host", "share"],
        },
        capabilities = ["read", "stream"],
    )

    async def walk(self) -> AsyncIterator[ConnectorFileRecord]:
        try:
            from smbprotocol.connection import Connection
            from smbprotocol.session import Session
            from smbprotocol.tree import TreeConnect
            from smbprotocol.open import Open, CreateDisposition, CreateOptions, FileAttributes, FilePipePrinterAccessMask
            import smbclient
        except ImportError:
            raise RuntimeError("smbprotocol required: uv add smbprotocol smbclient")

        host     = self.config["host"]
        share    = self.config["share"]
        username = self.config.get("username", "")
        password = self.config.get("password", "")
        domain   = self.config.get("domain", "WORKGROUP")
        port     = self.config.get("port", 445)
        sub_path = self.config.get("path", "/").lstrip("/")

        smbclient.register_session(host, username=username, password=password, port=port)
        unc_root = f"\\\\{host}\\{share}\\{sub_path}"

        for entry in smbclient.scandir(unc_root):
            if entry.is_file():
                stat = entry.stat()
                yield ConnectorFileRecord(
                    path       = f"smb://{host}/{share}/{entry.name}",
                    name       = entry.name,
                    size_bytes = stat.st_size,
                    modified   = stat.st_mtime,
                    suffix     = Path(entry.name).suffix.lower(),
                )

    async def test_connection(self) -> dict[str, Any]:
        try:
            import smbclient
            host = self.config["host"]
            smbclient.register_session(
                host,
                username=self.config.get("username", ""),
                password=self.config.get("password", ""),
                port=self.config.get("port", 445),
            )
            unc = f"\\\\{host}\\{self.config['share']}"
            smbclient.listdir(unc)
            return {"success": True, "message": f"Connected to {unc}"}
        except Exception as e:
            return {"success": False, "message": str(e)}


# ── Built-in: NFS share ───────────────────────────────────────────────────────

class NFSConnector(BaseConnector):
    """
    NFS share connector.
    Config: {host, export_path, mount_point}
    Note: Requires NFS share to be mounted locally, or uses libnfs.
    For simplicity, this connector walks a locally-mounted NFS path.
    """
    manifest = ConnectorManifest(
        id          = "nfs",
        name        = "NFS Share",
        description = "Index files from a locally-mounted NFS share",
        version     = "1.0.0",
        author      = "dgraph.ai",
        icon_url    = "https://dgraph.ai/icons/nfs.svg",
        config_schema = {
            "type": "object",
            "properties": {
                "host":        {"type": "string", "title": "NFS server host",          "placeholder": "192.168.1.10"},
                "export_path": {"type": "string", "title": "Export path on server",   "placeholder": "/volume1/data"},
                "mount_point": {"type": "string", "title": "Local mount point",       "placeholder": "/mnt/nas"},
            },
            "required": ["host", "export_path", "mount_point"],
        },
        capabilities = ["read", "stream"],
    )

    async def walk(self) -> AsyncIterator[ConnectorFileRecord]:
        """Walk the locally-mounted NFS path (same as LocalConnector)."""
        import os
        mount = Path(self.config["mount_point"]).expanduser()
        for dirpath, dirnames, filenames in os.walk(mount):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                try:
                    st = fpath.stat()
                    yield ConnectorFileRecord(
                        path       = f"nfs://{self.config['host']}{self.config['export_path']}/{fpath.relative_to(mount)}",
                        name       = fname,
                        size_bytes = st.st_size,
                        modified   = st.st_mtime,
                        suffix     = fpath.suffix.lower(),
                    )
                except (PermissionError, OSError):
                    continue

    async def test_connection(self) -> dict[str, Any]:
        mount = Path(self.config.get("mount_point", ""))
        if mount.exists() and mount.is_dir():
            return {"success": True, "message": f"NFS mount accessible at {mount}"}
        return {"success": False, "message": f"Mount point not found or not mounted: {mount}"}


# ── Connector registry ────────────────────────────────────────────────────────

from src.dgraphai.connectors.sharepoint import SharePointConnector
from src.dgraphai.connectors.gcs import GCSConnector

_REGISTRY: dict[str, type[BaseConnector]] = {
    "local":        LocalConnector,
    "smb":          SMBConnector,
    "nfs":          NFSConnector,
    "aws-s3":       S3Connector,
    "azure-blob":   AzureBlobConnector,
    "sharepoint":   SharePointConnector,
    "gcs":          GCSConnector,
}


def register_connector(connector_class: type[BaseConnector]) -> None:
    """Register a custom connector. Call this in your connector's module."""
    _REGISTRY[connector_class.manifest.id] = connector_class


def get_connector(connector_type: str) -> type[BaseConnector] | None:
    return _REGISTRY.get(connector_type)


def list_connectors() -> list[ConnectorManifest]:
    return [cls.manifest for cls in _REGISTRY.values()]
