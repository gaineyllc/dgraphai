"""
SAML 2.0 authentication (SP-initiated SSO).

Supports: Microsoft ADFS, Azure AD (legacy), Ping, Shibboleth, ADFS.
~30% of enterprise procurement requires SAML alongside OIDC.

Flow:
  1. User hits /api/auth/saml/{tenant_slug}/login
  2. We redirect to IdP with SAMLRequest
  3. IdP authenticates, POSTs SAMLResponse to /api/auth/saml/{tenant_slug}/acs
  4. We validate assertion, extract attributes, issue JWT

Each tenant configures their own SAML IdP via SAMLConfig.
Metadata XML downloaded from IdP or entered manually.

Attributes mapped:
  NameID   → user identifier (usually email)
  email    → from configurable attribute (default: emailaddress or email)
  name     → from configurable attribute (default: displayname or name)
  groups   → from configurable attribute → mapped to roles
"""
from __future__ import annotations
import os
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.db.models import Tenant, SAMLConfig, User
from src.dgraphai.db.session import get_db
from src.dgraphai.auth.oidc import get_auth_context, AuthContext

router  = APIRouter(prefix="/api/auth/saml", tags=["saml"])
APP_URL = os.getenv("APP_URL", "https://app.dgraph.ai")


async def _get_saml_config(tenant_slug: str, db: AsyncSession) -> tuple[Tenant, SAMLConfig]:
    tenant_r = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant   = tenant_r.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    config_r = await db.execute(
        select(SAMLConfig).where(SAMLConfig.tenant_id == tenant.id, SAMLConfig.is_active == True)
    )
    config = config_r.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="SAML not configured for this tenant")
    return tenant, config


@router.get("/{tenant_slug}/login")
async def saml_login(
    tenant_slug: str,
    relay_state: str = "/",
    db: AsyncSession = Depends(get_db),
):
    """Initiate SP-initiated SSO — redirect user to IdP."""
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
    except ImportError:
        raise HTTPException(status_code=501, detail="python3-saml not installed")

    tenant, config = await _get_saml_config(tenant_slug, db)
    settings = _build_saml_settings(tenant_slug, config)

    # Build minimal request object for python3-saml
    req = {
        "https":            "on" if APP_URL.startswith("https") else "off",
        "http_host":        APP_URL.replace("https://", "").replace("http://", ""),
        "script_name":      f"/api/auth/saml/{tenant_slug}/login",
        "server_port":      "443",
        "get_data":         {"RelayState": relay_state},
        "post_data":        {},
    }
    auth     = OneLogin_Saml2_Auth(req, settings)
    sso_url  = auth.login(return_to=relay_state)
    return RedirectResponse(url=sso_url)


@router.post("/{tenant_slug}/acs")
async def saml_acs(
    tenant_slug: str,
    request:     Request,
    db:          AsyncSession = Depends(get_db),
):
    """Assertion Consumer Service — receive SAMLResponse from IdP."""
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
    except ImportError:
        raise HTTPException(status_code=501, detail="python3-saml not installed")

    tenant, config = await _get_saml_config(tenant_slug, db)
    form           = await request.form()
    saml_response  = form.get("SAMLResponse", "")
    relay_state    = form.get("RelayState", "/")

    settings = _build_saml_settings(tenant_slug, config)
    req      = {
        "https":       "on" if APP_URL.startswith("https") else "off",
        "http_host":   APP_URL.replace("https://", "").replace("http://", ""),
        "script_name": f"/api/auth/saml/{tenant_slug}/acs",
        "server_port": "443",
        "get_data":    {},
        "post_data":   {"SAMLResponse": saml_response, "RelayState": relay_state},
    }
    auth = OneLogin_Saml2_Auth(req, settings)
    auth.process_response()

    errors = auth.get_errors()
    if errors:
        raise HTTPException(status_code=400, detail=f"SAML validation failed: {errors}")
    if not auth.is_authenticated():
        raise HTTPException(status_code=401, detail="SAML authentication failed")

    # Extract user attributes
    attrs   = auth.get_attributes()
    name_id = auth.get_nameid()
    email   = _first_attr(attrs, config.email_attribute or "emailaddress", name_id)
    name    = _first_attr(attrs, config.name_attribute or "displayname", email)
    groups  = attrs.get(config.groups_attribute or "groups", [])

    if not email:
        raise HTTPException(status_code=400, detail="Email attribute missing from SAML assertion")

    # JIT provisioning — create or update user
    result = await db.execute(
        select(User).where(User.email == email, User.tenant_id == tenant.id)
    )
    user = result.scalar_one_or_none()
    if not user:
        role = _map_groups_to_role(groups, config)
        user = User(
            tenant_id    = tenant.id,
            email        = email,
            display_name = name,
            name         = name,
            idp_provider = "saml",
            is_active    = True,
            email_verified = True,
            role         = role,
        )
        from sqlalchemy.ext.asyncio import AsyncSession
        db.add(user)
        await db.flush()
        from src.dgraphai.rbac.engine import assign_builtin_role
        await assign_builtin_role(user.id, tenant.id, role, db)
    else:
        user.display_name = name
        user.name         = name
        user.is_active    = True

    # Issue JWT and redirect to app
    from src.dgraphai.auth.local import _issue_jwt
    token = _issue_jwt(user, tenant)

    # Redirect to frontend with token (stored in URL fragment, JS reads it)
    redirect_url = f"{APP_URL}{relay_state}#token={token}"
    return HTMLResponse(content=f"""
    <html><body>
    <script>
      const url = new URL(window.location.href);
      const token = url.hash.split('token=')[1];
      if (token) {{ localStorage.setItem('dgraphai_token', token); window.location = '{relay_state}'; }}
    </script>
    <p>Redirecting...</p>
    </body></html>
    """)


@router.get("/{tenant_slug}/metadata")
async def saml_metadata(tenant_slug: str, db: AsyncSession = Depends(get_db)):
    """Return SP metadata XML for IdP configuration."""
    try:
        from onelogin.saml2.settings import OneLogin_Saml2_Settings
    except ImportError:
        raise HTTPException(status_code=501, detail="python3-saml not installed")

    tenant, config = await _get_saml_config(tenant_slug, db)
    settings = OneLogin_Saml2_Settings(_build_saml_settings(tenant_slug, config))
    metadata = settings.get_sp_metadata()
    return HTMLResponse(content=metadata, media_type="text/xml")


# ── SAML config management ─────────────────────────────────────────────────────

mgmt_router = APIRouter(prefix="/api/admin/saml", tags=["saml"])


class SAMLConfigRequest:
    idp_entity_id:    str
    idp_sso_url:      str
    idp_certificate:  str    # X.509 cert from IdP
    email_attribute:  str = "emailaddress"
    name_attribute:   str = "displayname"
    groups_attribute: str = "groups"
    role_mappings:    dict = {}  # {"admins": "admin", "analysts": "analyst"}


@mgmt_router.post("/config")
async def configure_saml(
    body: dict,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """Configure SAML for this tenant (admin only)."""
    if "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Admin required")

    # Disable existing config
    from sqlalchemy import update
    await db.execute(
        update(SAMLConfig).where(SAMLConfig.tenant_id == auth.tenant_id)
        .values(is_active=False)
    )

    config = SAMLConfig(
        tenant_id        = auth.tenant_id,
        idp_entity_id    = body["idp_entity_id"],
        idp_sso_url      = body["idp_sso_url"],
        idp_certificate  = body["idp_certificate"],
        email_attribute  = body.get("email_attribute", "emailaddress"),
        name_attribute   = body.get("name_attribute", "displayname"),
        groups_attribute = body.get("groups_attribute", "groups"),
        role_mappings    = body.get("role_mappings", {}),
        is_active        = True,
        created_by       = auth.user_id,
    )
    db.add(config)
    await db.flush()

    tenant_r = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant   = tenant_r.scalar_one_or_none()

    return {
        "status":        "configured",
        "login_url":     f"{APP_URL}/api/auth/saml/{tenant.slug}/login",
        "acs_url":       f"{APP_URL}/api/auth/saml/{tenant.slug}/acs",
        "metadata_url":  f"{APP_URL}/api/auth/saml/{tenant.slug}/metadata",
        "entity_id":     f"{APP_URL}/api/auth/saml/{tenant.slug}/metadata",
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_saml_settings(tenant_slug: str, config: SAMLConfig) -> dict:
    sp_base = f"{APP_URL}/api/auth/saml/{tenant_slug}"
    return {
        "strict": True,
        "debug":  False,
        "sp": {
            "entityId": f"{sp_base}/metadata",
            "assertionConsumerService": {
                "url":     f"{sp_base}/acs",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        },
        "idp": {
            "entityId": config.idp_entity_id,
            "singleSignOnService": {
                "url":     config.idp_sso_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": config.idp_certificate,
        },
        "security": {
            "wantAssertionsSigned":  True,
            "wantMessagesSigned":    True,
            "signatureAlgorithm":    "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
        },
    }


def _first_attr(attrs: dict, key: str, default: str = "") -> str:
    val = attrs.get(key, attrs.get(key.lower(), []))
    return val[0] if val else default


def _map_groups_to_role(groups: list[str], config: SAMLConfig) -> str:
    mappings = config.role_mappings or {}
    for group in groups:
        if group in mappings:
            return mappings[group]
        if "admin" in group.lower():
            return "admin"
        if "analyst" in group.lower():
            return "analyst"
    return "viewer"
