"""
dgraph.ai Licensing System
───────────────────────────
Cryptographic license files using Ed25519 signatures (RFC 8037).

License file format (.dglicense):
  Base64-encoded JSON payload + Ed25519 signature
  Verified offline — zero phone-home required for air-gapped deployments

License payload fields:
  license_id:      UUID — unique identifier
  issued_to:       Company name
  issued_to_email: Contact email
  license_type:    saas | self-hosted | air-gapped | trial
  issued_at:       ISO timestamp
  expires_at:      ISO timestamp or null (perpetual)
  grace_period_days: int — days after expiry before hard cutoff
  hardware_fingerprint: optional — binds to specific machine/cluster
  features:        dict of feature flags
  limits:          dict of resource limits

Feature flags:
  graph_visualization:  bool
  saved_queries:        bool
  approval_workflows:   bool
  scanner_agents:       int  (max concurrent agents)
  ai_training_export:   bool
  sso_oidc:             bool
  custom_roles:         bool
  audit_log_stream:     bool
  api_access:           bool
  compliance_reports:   bool

Limits:
  max_tenants:    int
  max_users:      int  (per tenant)
  max_connectors: int  (per tenant)
  max_nodes:      int  (per tenant, millions)
  max_exports:    int  (per month, -1 = unlimited)

Key management:
  Private key: kept offline by dgraph.ai, used only to sign licenses
  Public key:  embedded in the application binary at build time
  Rotation:    new public key deployed with new version; old licenses still valid
               if they were signed with any key in the trusted key set
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey
)
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat,
    load_pem_private_key, load_pem_public_key
)


# ── Trusted public keys (embedded at build time) ──────────────────────────────
# In production: replace with actual public key(s).
# Multiple keys supported for rotation — any match validates.
# Key IDs are SHA-256 fingerprints of the DER-encoded public key.

TRUSTED_PUBLIC_KEYS_PEM: list[str] = [
    # Key ID: dev-2026-04 (replace with production key)
    """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAREPLACEWITHREALKEYINPRODUCTION0000000000000000000
-----END PUBLIC KEY-----""",
]


class LicenseType(str, Enum):
    SAAS        = "saas"
    SELF_HOSTED = "self-hosted"
    AIR_GAPPED  = "air-gapped"
    TRIAL       = "trial"
    DEVELOPER   = "developer"


@dataclass
class LicenseFeatures:
    graph_visualization:  bool = True
    saved_queries:        bool = True
    approval_workflows:   bool = True
    scanner_agents:       int  = 1
    ai_training_export:   bool = False
    sso_oidc:             bool = False
    custom_roles:         bool = False
    audit_log_stream:     bool = False
    api_access:           bool = True
    compliance_reports:   bool = False


@dataclass
class LicenseLimits:
    max_tenants:    int = 1
    max_users:      int = 10
    max_connectors: int = 3
    max_nodes:      int = 500_000      # per tenant
    max_exports:    int = 10           # per month, -1 = unlimited


@dataclass
class License:
    license_id:            str
    issued_to:             str
    issued_to_email:       str
    license_type:          LicenseType
    issued_at:             datetime
    expires_at:            datetime | None
    grace_period_days:     int
    hardware_fingerprint:  str | None
    features:              LicenseFeatures
    limits:                LicenseLimits
    metadata:              dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        now = datetime.now(timezone.utc)
        if self.expires_at.tzinfo is None:
            expires = self.expires_at.replace(tzinfo=timezone.utc)
        else:
            expires = self.expires_at
        return now > expires

    @property
    def is_in_grace_period(self) -> bool:
        if self.expires_at is None:
            return False
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        if self.expires_at.tzinfo is None:
            expires = self.expires_at.replace(tzinfo=timezone.utc)
        else:
            expires = self.expires_at
        grace_end = expires + timedelta(days=self.grace_period_days)
        return expires < now <= grace_end

    @property
    def is_valid(self) -> bool:
        """True if license is active (not expired beyond grace period)."""
        if self.expires_at is None:
            return True
        if self.is_in_grace_period:
            return True
        return not self.is_expired

    def check_feature(self, feature: str) -> bool:
        return bool(getattr(self.features, feature, False))

    def days_until_expiry(self) -> int | None:
        if self.expires_at is None:
            return None
        if self.expires_at.tzinfo is None:
            expires = self.expires_at.replace(tzinfo=timezone.utc)
        else:
            expires = self.expires_at
        delta = expires - datetime.now(timezone.utc)
        return max(0, delta.days)


# ── License serialization ─────────────────────────────────────────────────────

def _license_to_payload(license: License) -> dict[str, Any]:
    return {
        "license_id":           license.license_id,
        "issued_to":            license.issued_to,
        "issued_to_email":      license.issued_to_email,
        "license_type":         license.license_type,
        "issued_at":            license.issued_at.isoformat(),
        "expires_at":           license.expires_at.isoformat() if license.expires_at else None,
        "grace_period_days":    license.grace_period_days,
        "hardware_fingerprint": license.hardware_fingerprint,
        "features": {
            "graph_visualization":  license.features.graph_visualization,
            "saved_queries":        license.features.saved_queries,
            "approval_workflows":   license.features.approval_workflows,
            "scanner_agents":       license.features.scanner_agents,
            "ai_training_export":   license.features.ai_training_export,
            "sso_oidc":             license.features.sso_oidc,
            "custom_roles":         license.features.custom_roles,
            "audit_log_stream":     license.features.audit_log_stream,
            "api_access":           license.features.api_access,
            "compliance_reports":   license.features.compliance_reports,
        },
        "limits": {
            "max_tenants":    license.limits.max_tenants,
            "max_users":      license.limits.max_users,
            "max_connectors": license.limits.max_connectors,
            "max_nodes":      license.limits.max_nodes,
            "max_exports":    license.limits.max_exports,
        },
        "metadata": license.metadata,
    }


def _payload_to_license(payload: dict[str, Any]) -> License:
    features = LicenseFeatures(**payload.get("features", {}))
    limits   = LicenseLimits(**payload.get("limits", {}))
    return License(
        license_id           = payload["license_id"],
        issued_to            = payload["issued_to"],
        issued_to_email      = payload["issued_to_email"],
        license_type         = LicenseType(payload["license_type"]),
        issued_at            = datetime.fromisoformat(payload["issued_at"]),
        expires_at           = datetime.fromisoformat(payload["expires_at"]) if payload.get("expires_at") else None,
        grace_period_days    = payload.get("grace_period_days", 14),
        hardware_fingerprint = payload.get("hardware_fingerprint"),
        features             = features,
        limits               = limits,
        metadata             = payload.get("metadata", {}),
    )


# ── License signing (used by dgraph.ai license portal — private key offline) ──

def sign_license(license: License, private_key_pem: str) -> str:
    """
    Sign a license with the dgraph.ai private key.
    Returns a .dglicense file content (base64 payload + signature).
    Call this from the license issuance service — private key never
    leaves dgraph.ai infrastructure.
    """
    private_key = load_pem_private_key(private_key_pem.encode(), password=None)
    payload     = _license_to_payload(license)
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signature   = private_key.sign(payload_bytes)

    license_file = {
        "version":   "1",
        "payload":   base64.b64encode(payload_bytes).decode(),
        "signature": base64.b64encode(signature).decode(),
    }
    return base64.b64encode(json.dumps(license_file).encode()).decode()


# ── License verification (runs in the application — public key only) ──────────

class LicenseError(Exception):
    pass


def verify_license(license_b64: str) -> License:
    """
    Verify a .dglicense file and return the decoded License.
    Raises LicenseError if the signature is invalid or the license is expired.
    Runs fully offline — no network call required.
    """
    try:
        license_file = json.loads(base64.b64decode(license_b64))
        payload_bytes = base64.b64decode(license_file["payload"])
        signature     = base64.b64decode(license_file["signature"])
    except Exception as e:
        raise LicenseError(f"Invalid license file format: {e}")

    # Try each trusted public key
    verified = False
    for key_pem in TRUSTED_PUBLIC_KEYS_PEM:
        try:
            public_key = load_pem_public_key(key_pem.strip().encode())
            public_key.verify(signature, payload_bytes)
            verified = True
            break
        except Exception:
            continue

    if not verified:
        raise LicenseError("License signature verification failed — license may be tampered or from an unknown issuer")

    payload = json.loads(payload_bytes)
    license = _payload_to_license(payload)

    # Hardware fingerprint check (if bound)
    if license.hardware_fingerprint:
        current_fp = get_hardware_fingerprint()
        if current_fp != license.hardware_fingerprint:
            raise LicenseError(
                "License is bound to a different machine. "
                "Contact support@dgraph.ai to transfer your license."
            )

    if not license.is_valid:
        if license.is_expired and not license.is_in_grace_period:
            raise LicenseError(
                f"License expired on {license.expires_at.date()} "
                f"(grace period of {license.grace_period_days} days has passed). "
                "Contact support@dgraph.ai to renew."
            )

    return license


# ── Hardware fingerprinting ───────────────────────────────────────────────────

def get_hardware_fingerprint() -> str:
    """
    Generate a hardware fingerprint for license binding.
    Uses stable hardware identifiers — survives reboots but not hardware changes.
    For K8s: uses cluster UID from kube-system namespace (stable).
    """
    components: list[str] = []

    # Try K8s cluster UID first (stable in Kubernetes)
    k8s_uid = _get_k8s_cluster_uid()
    if k8s_uid:
        components.append(f"k8s:{k8s_uid}")
    else:
        # Bare metal / Docker: use MAC address + hostname
        import uuid as _uuid
        mac = _uuid.getnode()
        components.append(f"mac:{mac:012x}")
        components.append(f"host:{platform.node()}")

        # Add CPU info for additional entropy
        if platform.system() == "Linux":
            try:
                cpu_id = Path("/proc/cpuinfo").read_text().split("\n")[0]
                components.append(f"cpu:{hashlib.md5(cpu_id.encode()).hexdigest()[:8]}")
            except Exception:
                pass

    fingerprint_str = "|".join(sorted(components))
    return hashlib.sha256(fingerprint_str.encode()).hexdigest()


def _get_k8s_cluster_uid() -> str | None:
    """Get the Kubernetes cluster UID from the kube-system namespace."""
    try:
        import kubernetes  # type: ignore
        kubernetes.config.load_incluster_config()
        v1 = kubernetes.client.CoreV1Api()
        ns = v1.read_namespace("kube-system")
        return str(ns.metadata.uid)
    except Exception:
        return None


# ── License loading ───────────────────────────────────────────────────────────

def load_license() -> License:
    """
    Load and verify the license from the configured path or env var.
    Search order:
      1. DGRAPHAI_LICENSE env var (base64 license content)
      2. DGRAPHAI_LICENSE_FILE env var (path to .dglicense file)
      3. /etc/dgraphai/license.dglicense (default location)
      4. ~/.dgraphai/license.dglicense (user home)
      5. Built-in developer license (limited features, for local dev)
    """
    # 1. Env var (for K8s secrets)
    license_b64 = os.getenv("DGRAPHAI_LICENSE")
    if license_b64:
        return verify_license(license_b64)

    # 2. File path from env
    license_path = os.getenv("DGRAPHAI_LICENSE_FILE")
    if license_path:
        content = Path(license_path).read_text().strip()
        return verify_license(content)

    # 3. Default system path
    for path in [
        Path("/etc/dgraphai/license.dglicense"),
        Path.home() / ".dgraphai" / "license.dglicense",
    ]:
        if path.exists():
            return verify_license(path.read_text().strip())

    # 4. Developer fallback — limited but functional for local dev
    return _developer_license()


def _developer_license() -> License:
    """
    Built-in developer license for local development.
    No signature required — detected by absence of a real license file.
    Clearly marked as dev, limited features, watermarks in exports.
    """
    return License(
        license_id           = "dev-local-00000000-0000-0000-0000-000000000000",
        issued_to            = "Developer (local)",
        issued_to_email      = "dev@localhost",
        license_type         = LicenseType.DEVELOPER,
        issued_at            = datetime.now(timezone.utc),
        expires_at           = None,
        grace_period_days    = 0,
        hardware_fingerprint = None,
        features             = LicenseFeatures(
            graph_visualization = True,
            saved_queries       = True,
            approval_workflows  = True,
            scanner_agents      = 1,
            ai_training_export  = True,  # dev: all features enabled
            sso_oidc            = False,  # dev: SSO disabled (use dev auth)
            custom_roles        = True,
            audit_log_stream    = False,
            api_access          = True,
            compliance_reports  = False,
        ),
        limits = LicenseLimits(
            max_tenants    = 1,
            max_users      = 5,
            max_connectors = 2,
            max_nodes      = 100_000,
            max_exports    = 10,
        ),
        metadata = {"dev_mode": True},
    )


# ── Application-level license singleton ───────────────────────────────────────

_current_license: License | None = None


def get_license() -> License:
    """Return the current loaded license (cached)."""
    global _current_license
    if _current_license is None:
        _current_license = load_license()
    return _current_license


def require_feature(feature: str) -> None:
    """Raise LicenseError if the feature is not enabled in the current license."""
    lic = get_license()
    if not lic.check_feature(feature):
        raise LicenseError(
            f"Feature '{feature}' is not available in your {lic.license_type} license. "
            "Contact sales@dgraph.ai to upgrade."
        )
