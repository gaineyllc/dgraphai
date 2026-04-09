/**
 * Development environment — uses all integration test modules.
 *
 * Usage:
 *   cd terraform/environments/dev
 *   cp terraform.tfvars.example terraform.tfvars
 *   # Fill in secrets in terraform.tfvars (gitignored)
 *   terraform init
 *   terraform plan
 *   terraform apply
 *   terraform output -json | python3 ../../scripts/write_env.py > ../../../.env.test
 */

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws    = { source = "hashicorp/aws",   version = "~> 5.0" }
    stripe = { source = "lukasaron/stripe",version = "~> 1.9" }
    okta   = { source = "okta/okta",       version = "~> 4.8" }
    random = { source = "hashicorp/random", version = "~> 3.0" }
  }
}

variable "stripe_secret_key" { type = string; sensitive = true }
variable "okta_org_name"     { type = string }
variable "okta_api_token"    { type = string; sensitive = true }
variable "neo4j_password"    { type = string; sensitive = true; default = "TestNeo4j2026!" }
variable "app_url"           { type = string; default = "https://dev.dgraph.ai" }

provider "aws" {
  region = "us-east-1"
  default_tags { tags = { Environment = "dev", ManagedBy = "terraform", Project = "dgraphai" } }
}

provider "stripe" { api_key = var.stripe_secret_key }

provider "okta" {
  org_name  = var.okta_org_name
  base_url  = "oktapreview.com"
  api_token = var.okta_api_token
}

# ── Stripe module ───────────────────────────────────────────────────────────────

module "stripe" {
  source         = "../../modules/stripe"
  app_url        = var.app_url
  stripe_api_key = var.stripe_secret_key
}

# ── Okta module ─────────────────────────────────────────────────────────────────

module "okta" {
  source      = "../../modules/okta"
  app_url     = var.app_url
  tenant_slug = "dev"
}

# ── AWS module (Neo4j + S3) ─────────────────────────────────────────────────────

module "aws" {
  source          = "../../modules/aws"
  environment     = "dev"
  neo4j_password  = var.neo4j_password
  allowed_cidr    = "0.0.0.0/0"   # CHANGE to your IP in production
}

# ── Combined env output ──────────────────────────────────────────────────────────

output "all_env_vars" {
  description = "All environment variables for .env.test"
  sensitive   = true
  value = <<-EOT
    # === STRIPE ===
    STRIPE_PRICE_PRO=${module.stripe.stripe_price_pro_monthly}
    STRIPE_PRICE_BUSINESS=${module.stripe.stripe_price_business_monthly}
    STRIPE_WEBHOOK_SECRET=${module.stripe.stripe_webhook_secret}

    # === NEO4J (AWS) ===
    NEO4J_URI=${module.aws.neo4j_bolt_uri}
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=${var.neo4j_password}

    # === S3 SCANNER TEST ===
    S3_TEST_BUCKET=${module.aws.s3_bucket_name}
    AWS_ACCESS_KEY_ID=${module.aws.scanner_access_key}
    AWS_SECRET_ACCESS_KEY=${module.aws.scanner_secret_key}

    # === OKTA SAML (paste certificate manually) ===
    OKTA_SAML_SSO_URL=${module.okta.saml_sso_url}
    OKTA_SAML_ISSUER=${module.okta.saml_issuer}
    # OKTA_SAML_CERTIFICATE=<from Okta app Sign On tab>
  EOT
}

output "neo4j_browser" { value = module.aws.neo4j_browser_url }
output "saml_config"   { value = module.okta.saml_config_snippet; sensitive = true }
