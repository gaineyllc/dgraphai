"""
Keycloak realm provisioner — run once to configure Keycloak for dgraph.ai.

Creates:
  - A 'dgraphai' realm
  - A client configured for dgraph.ai OIDC
  - Default roles: admin, analyst, viewer

Usage (run after Keycloak starts):
  python -m src.dgraphai.auth.keycloak_setup --url http://keycloak:8080 --admin-password YOURPASS
"""
from __future__ import annotations

import os
import sys

import httpx


REALM_NAME    = "dgraphai"
CLIENT_ID     = "dgraphai-app"
CLIENT_SECRET = os.getenv("DGRAPHAI_OIDC_CLIENT_SECRET", "dgraphai-secret-change-me")


def _admin_token(base_url: str, password: str) -> str:
    r = httpx.post(
        f"{base_url}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id":  "admin-cli",
            "username":   "admin",
            "password":   password,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def provision(base_url: str, admin_password: str, app_base_url: str = "https://app.dgraph.ai") -> None:
    """Configure Keycloak realm + client for dgraph.ai."""
    token = _admin_token(base_url, admin_password)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # ── Create realm ──────────────────────────────────────────────────────────
    r = httpx.post(
        f"{base_url}/admin/realms",
        headers=headers,
        json={
            "realm":           REALM_NAME,
            "enabled":         True,
            "displayName":     "dgraph.ai",
            "loginTheme":      "keycloak",
            "registrationAllowed": False,
            "resetPasswordAllowed": True,
            "bruteForceProtected": True,
            "accessTokenLifespan": 3600,
        },
        timeout=15,
    )
    if r.status_code == 409:
        print(f"Realm '{REALM_NAME}' already exists — skipping creation")
    else:
        r.raise_for_status()
        print(f"✅ Realm '{REALM_NAME}' created")

    # ── Create OIDC client ────────────────────────────────────────────────────
    r = httpx.post(
        f"{base_url}/admin/realms/{REALM_NAME}/clients",
        headers=headers,
        json={
            "clientId":                  CLIENT_ID,
            "secret":                    CLIENT_SECRET,
            "enabled":                   True,
            "protocol":                  "openid-connect",
            "publicClient":              False,
            "standardFlowEnabled":       True,
            "serviceAccountsEnabled":    True,
            "directAccessGrantsEnabled": False,
            "redirectUris": [
                f"{app_base_url}/*",
                "http://localhost:5173/*",   # Vite dev server
            ],
            "webOrigins": [app_base_url, "http://localhost:5173"],
            "attributes": {
                "access.token.lifespan": "3600",
            },
        },
        timeout=15,
    )
    if r.status_code == 409:
        print(f"Client '{CLIENT_ID}' already exists — skipping")
    else:
        r.raise_for_status()
        print(f"✅ Client '{CLIENT_ID}' created")

    # ── Create realm roles ────────────────────────────────────────────────────
    for role in ["admin", "analyst", "viewer"]:
        r = httpx.post(
            f"{base_url}/admin/realms/{REALM_NAME}/roles",
            headers=headers,
            json={"name": role, "description": f"dgraph.ai {role} role"},
            timeout=15,
        )
        if r.status_code not in (201, 409):
            r.raise_for_status()

    print("✅ Roles created: admin, analyst, viewer")

    # ── Print OIDC config for dgraph.ai ───────────────────────────────────────
    issuer_url = f"{base_url}/realms/{REALM_NAME}"
    print()
    print("=" * 60)
    print("OIDC configuration for dgraph.ai:")
    print(f"  Provider name:  Keycloak (self-hosted)")
    print(f"  Issuer URL:     {issuer_url}")
    print(f"  Client ID:      {CLIENT_ID}")
    print(f"  Client Secret:  {CLIENT_SECRET}")
    print(f"  Claim mapping:  {{\"email\": \"email\", \"name\": \"name\", \"groups\": \"roles\"}}")
    print()
    print("Add this via: POST /api/auth/oidc  (or via the Settings UI)")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Provision Keycloak for dgraph.ai")
    p.add_argument("--url",            default="http://localhost:8080", help="Keycloak base URL")
    p.add_argument("--admin-password", required=True, help="Keycloak admin password")
    p.add_argument("--app-url",        default="https://app.dgraph.ai", help="dgraph.ai app URL")
    args = p.parse_args()
    provision(args.url, args.admin_password, args.app_url)
