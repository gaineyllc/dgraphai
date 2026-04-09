"""
License key generation — runs at dgraph.ai HQ only.
Private key never ships with the product.

Usage (run offline, on air-gapped signing machine):
  python -m src.dgraphai.licensing.keygen generate-keypair
  python -m src.dgraphai.licensing.keygen issue --config license.json
  python -m src.dgraphai.licensing.keygen verify --file customer.dglicense
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat
)

from src.dgraphai.licensing.license import (
    License, LicenseFeatures, LicenseLimits, LicenseType,
    sign_license, verify_license, get_hardware_fingerprint
)


def generate_keypair(output_dir: str = ".") -> tuple[str, str]:
    """
    Generate a new Ed25519 keypair for license signing.
    Private key: store offline, NEVER commit to git.
    Public key: embed in application at build time.
    """
    private_key = Ed25519PrivateKey.generate()
    public_key  = private_key.public_key()

    priv_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    pub_pem  = public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()

    out = Path(output_dir)
    (out / "dgraphai_signing_private.pem").write_text(priv_pem)
    (out / "dgraphai_signing_public.pem").write_text(pub_pem)

    print("✅ Keypair generated:")
    print(f"   Private key: {out}/dgraphai_signing_private.pem")
    print(f"   Public key:  {out}/dgraphai_signing_public.pem")
    print()
    print("⚠️  Store the private key offline and NEVER commit it to git.")
    print("   Embed the public key in src/dgraphai/licensing/license.py")

    return priv_pem, pub_pem


def issue_license(
    private_key_path: str,
    issued_to: str,
    issued_to_email: str,
    license_type: str = "self-hosted",
    expires_days: int | None = 365,
    max_tenants: int = 1,
    max_users: int = 50,
    max_connectors: int = 10,
    max_nodes: int = 5_000_000,
    features: dict | None = None,
    hardware_fingerprint: str | None = None,
    grace_period_days: int = 14,
) -> str:
    """Issue a signed license file."""
    private_key_pem = Path(private_key_path).read_text()

    feat = LicenseFeatures()
    if features:
        for k, v in features.items():
            setattr(feat, k, v)

    limits = LicenseLimits(
        max_tenants    = max_tenants,
        max_users      = max_users,
        max_connectors = max_connectors,
        max_nodes      = max_nodes,
    )

    now = datetime.now(timezone.utc)
    license = License(
        license_id           = str(uuid.uuid4()),
        issued_to            = issued_to,
        issued_to_email      = issued_to_email,
        license_type         = LicenseType(license_type),
        issued_at            = now,
        expires_at           = now + timedelta(days=expires_days) if expires_days else None,
        grace_period_days    = grace_period_days,
        hardware_fingerprint = hardware_fingerprint,
        features             = feat,
        limits               = limits,
    )

    return sign_license(license, private_key_pem)


def issue_trial(private_key_path: str, email: str, company: str) -> str:
    """Issue a 14-day trial license."""
    return issue_license(
        private_key_path = private_key_path,
        issued_to        = company,
        issued_to_email  = email,
        license_type     = "trial",
        expires_days     = 14,
        max_tenants      = 1,
        max_users        = 5,
        max_connectors   = 2,
        max_nodes        = 100_000,
        grace_period_days = 3,
        features = {
            "graph_visualization":  True,
            "saved_queries":        True,
            "approval_workflows":   True,
            "scanner_agents":       1,
            "ai_training_export":   True,
            "sso_oidc":             False,
            "custom_roles":         False,
            "audit_log_stream":     False,
            "api_access":           True,
            "compliance_reports":   False,
        },
    )


def issue_air_gapped(
    private_key_path: str,
    email: str,
    company: str,
    bind_to_hardware: bool = True,
) -> str:
    """Issue an air-gapped perpetual license, optionally bound to hardware."""
    fp = get_hardware_fingerprint() if bind_to_hardware else None
    return issue_license(
        private_key_path     = private_key_path,
        issued_to            = company,
        issued_to_email      = email,
        license_type         = "air-gapped",
        expires_days         = None,   # perpetual
        max_tenants          = 1,
        max_users            = 100,
        max_connectors       = 20,
        max_nodes            = 50_000_000,
        hardware_fingerprint = fp,
        grace_period_days    = 0,
        features = {
            "graph_visualization":  True,
            "saved_queries":        True,
            "approval_workflows":   True,
            "scanner_agents":       10,
            "ai_training_export":   True,
            "sso_oidc":             True,
            "custom_roles":         True,
            "audit_log_stream":     True,
            "api_access":           True,
            "compliance_reports":   True,
        },
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="dgraph.ai license keygen")
    sub = parser.add_subparsers(dest="cmd")

    # generate-keypair
    sub.add_parser("generate-keypair")

    # issue
    issue_p = sub.add_parser("issue")
    issue_p.add_argument("--key",    required=True, help="Path to private key PEM")
    issue_p.add_argument("--email",  required=True)
    issue_p.add_argument("--company",required=True)
    issue_p.add_argument("--type",   default="self-hosted",
                        choices=["saas","self-hosted","air-gapped","trial"])
    issue_p.add_argument("--days",   type=int, default=365)
    issue_p.add_argument("--output", default="license.dglicense")

    # trial
    trial_p = sub.add_parser("trial")
    trial_p.add_argument("--key",    required=True)
    trial_p.add_argument("--email",  required=True)
    trial_p.add_argument("--company",required=True)
    trial_p.add_argument("--output", default="trial.dglicense")

    # verify
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("--file", required=True)

    # fingerprint
    sub.add_parser("fingerprint")

    args = parser.parse_args()

    if args.cmd == "generate-keypair":
        generate_keypair()

    elif args.cmd == "issue":
        lic = issue_license(args.key, args.company, args.email,
                           license_type=args.type, expires_days=args.days)
        Path(args.output).write_text(lic)
        print(f"✅ License written to {args.output}")

    elif args.cmd == "trial":
        lic = issue_trial(args.key, args.email, args.company)
        Path(args.output).write_text(lic)
        print(f"✅ Trial license written to {args.output}")

    elif args.cmd == "verify":
        content = Path(args.file).read_text().strip()
        try:
            lic = verify_license(content)
            print(f"✅ Valid license")
            print(f"   Issued to:   {lic.issued_to} <{lic.issued_to_email}>")
            print(f"   Type:        {lic.license_type}")
            print(f"   Expires:     {lic.expires_at or 'Never (perpetual)'}")
            print(f"   Days left:   {lic.days_until_expiry() or 'N/A'}")
            print(f"   Features:    {[k for k,v in vars(lic.features).items() if v]}")
        except Exception as e:
            print(f"✗  {e}", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "fingerprint":
        fp = get_hardware_fingerprint()
        print(f"Hardware fingerprint: {fp}")
        print("Use this when issuing an air-gapped hardware-bound license.")

    else:
        parser.print_help()
