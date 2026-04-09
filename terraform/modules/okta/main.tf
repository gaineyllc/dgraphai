/**
 * Okta setup for dgraph.ai SCIM + SAML integration tests.
 *
 * Creates:
 *   - SCIM 2.0 provisioning application
 *   - SAML 2.0 SSO application
 *   - Test groups: dgraphai-admins, dgraphai-analysts, dgraphai-viewers
 *   - Test users assigned to groups
 *   - Group → role mapping configuration
 *
 * After apply:
 *   1. Copy SAML metadata from Okta app to dgraph.ai SAML config
 *   2. Generate SCIM token in dgraph.ai, paste into Okta provisioning config
 *   3. Run Okta "Test Connection" to verify SCIM
 *   4. Assign a test user and verify JIT provisioning
 */

terraform {
  required_providers {
    okta = {
      source  = "okta/okta"
      version = "~> 4.8"
    }
  }
}

variable "app_url"        { type = string }
variable "tenant_slug"    { type = string; default = "test-tenant" }
variable "scim_token"     { type = string; sensitive = true; default = "" }

# ── Groups ──────────────────────────────────────────────────────────────────────

resource "okta_group" "admins" {
  name        = "dgraphai-admins"
  description = "dgraph.ai administrators — mapped to admin role"
}

resource "okta_group" "analysts" {
  name        = "dgraphai-analysts"
  description = "dgraph.ai analysts — mapped to analyst role"
}

resource "okta_group" "viewers" {
  name        = "dgraphai-viewers"
  description = "dgraph.ai viewers — mapped to viewer role"
}

# ── Test users ──────────────────────────────────────────────────────────────────

resource "okta_user" "admin_test" {
  first_name  = "Admin"
  last_name   = "Test"
  login       = "admin.test@example.com"
  email       = "admin.test@example.com"
  status      = "ACTIVE"
}

resource "okta_group_memberships" "admin_membership" {
  group_id = okta_group.admins.id
  users    = [okta_user.admin_test.id]
}

resource "okta_user" "analyst_test" {
  first_name = "Analyst"
  last_name  = "Test"
  login      = "analyst.test@example.com"
  email      = "analyst.test@example.com"
  status     = "ACTIVE"
}

resource "okta_group_memberships" "analyst_membership" {
  group_id = okta_group.analysts.id
  users    = [okta_user.analyst_test.id]
}

# ── SCIM 2.0 application ────────────────────────────────────────────────────────

resource "okta_app_oauth" "dgraphai_scim" {
  label          = "dgraph.ai (SCIM)"
  type           = "service"
  grant_types    = ["client_credentials"]
  response_types = ["token"]
  token_endpoint_auth_method = "client_secret_basic"

  lifecycle {
    ignore_changes = [client_secret]
  }
}

# Note: Okta SCIM provisioning config is done in the Okta admin UI
# after applying. The base URL and bearer token from dgraph.ai admin
# must be entered manually. Terraform manages the app shell.

# ── SAML 2.0 application ────────────────────────────────────────────────────────

resource "okta_app_saml" "dgraphai_saml" {
  label             = "dgraph.ai"
  sso_url           = "${var.app_url}/api/auth/saml/${var.tenant_slug}/acs"
  recipient         = "${var.app_url}/api/auth/saml/${var.tenant_slug}/acs"
  destination       = "${var.app_url}/api/auth/saml/${var.tenant_slug}/acs"
  audience          = "${var.app_url}/api/auth/saml/${var.tenant_slug}/metadata"
  subject_name_id_template = "$${user.email}"
  subject_name_id_format   = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
  response_signed   = true
  signature_algorithm      = "RSA_SHA256"
  digest_algorithm  = "SHA256"
  honor_force_authn = false
  authn_context_class_ref  = "urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport"

  # Attribute statements for dgraph.ai
  attribute_statements {
    name      = "email"
    namespace = "urn:oasis:names:tc:SAML:2.0:attrname-format:basic"
    values    = ["$${user.email}"]
  }
  attribute_statements {
    name      = "displayname"
    namespace = "urn:oasis:names:tc:SAML:2.0:attrname-format:basic"
    values    = ["$${user.displayName}"]
  }
  attribute_statements {
    name      = "groups"
    namespace = "urn:oasis:names:tc:SAML:2.0:attrname-format:basic"
    filter_type  = "STARTS_WITH"
    filter_value = "dgraphai-"
  }
}

# Assign test groups to SAML app
resource "okta_app_group_assignment" "saml_admins" {
  app_id   = okta_app_saml.dgraphai_saml.id
  group_id = okta_group.admins.id
}

resource "okta_app_group_assignment" "saml_analysts" {
  app_id   = okta_app_saml.dgraphai_saml.id
  group_id = okta_group.analysts.id
}

# ── Outputs ─────────────────────────────────────────────────────────────────────

output "saml_metadata_url" {
  description = "Paste this URL into dgraph.ai SAML config to fetch IdP metadata"
  value       = "https://${var.tenant_slug}.okta.com/app/${okta_app_saml.dgraphai_saml.id}/sso/saml/metadata"
}

output "saml_sso_url" {
  description = "IdP SSO URL for dgraph.ai SAML config"
  value       = okta_app_saml.dgraphai_saml.http_post_binding
}

output "saml_issuer" {
  description = "IdP Entity ID for dgraph.ai SAML config"
  value       = okta_app_saml.dgraphai_saml.entity_url
}

output "admin_test_email"   { value = okta_user.admin_test.email }
output "analyst_test_email" { value = okta_user.analyst_test.email }

output "saml_config_snippet" {
  description = "POST to /api/admin/saml/config to configure SAML"
  value = jsonencode({
    idp_entity_id    = okta_app_saml.dgraphai_saml.entity_url
    idp_sso_url      = okta_app_saml.dgraphai_saml.http_post_binding
    idp_certificate  = "(get from Okta app > Sign On > Certificate)"
    email_attribute  = "email"
    name_attribute   = "displayname"
    groups_attribute = "groups"
    role_mappings = {
      "dgraphai-admins"   = "admin"
      "dgraphai-analysts" = "analyst"
      "dgraphai-viewers"  = "viewer"
    }
  })
}
