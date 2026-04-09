/**
 * Stripe test mode setup for dgraph.ai billing integration tests.
 *
 * Creates:
 *   - Product: dgraph.ai Pro
 *   - Product: dgraph.ai Business
 *   - Price: Pro monthly ($299/mo)
 *   - Price: Pro annual ($2990/yr — 2 months free)
 *   - Price: Business monthly ($999/mo)
 *   - Webhook endpoint pointing to the test app
 *
 * After apply, paste outputs into .env:
 *   STRIPE_SECRET_KEY=sk_test_...
 *   STRIPE_PRICE_PRO=price_...
 *   STRIPE_PRICE_BUSINESS=price_...
 *   STRIPE_WEBHOOK_SECRET=whsec_...
 */

terraform {
  required_providers {
    stripe = {
      source  = "lukasaron/stripe"
      version = "~> 1.9"
    }
  }
}

variable "app_url"         { type = string }
variable "stripe_api_key"  { type = string; sensitive = true }

# ── Products ────────────────────────────────────────────────────────────────────

resource "stripe_product" "pro" {
  name        = "dgraph.ai Pro"
  description = "Enterprise filesystem knowledge graph — Pro tier"
  active      = true
  metadata = {
    plan      = "pro"
    tier      = "2"
  }
}

resource "stripe_product" "business" {
  name        = "dgraph.ai Business"
  description = "Enterprise filesystem knowledge graph — Business tier"
  active      = true
  metadata = {
    plan      = "business"
    tier      = "3"
  }
}

# ── Prices ──────────────────────────────────────────────────────────────────────

resource "stripe_price" "pro_monthly" {
  product     = stripe_product.pro.id
  currency    = "usd"
  unit_amount = 29900   # $299.00
  recurring {
    interval       = "month"
    interval_count = 1
  }
  metadata = {
    plan     = "pro"
    billing  = "monthly"
  }
}

resource "stripe_price" "pro_annual" {
  product     = stripe_product.pro.id
  currency    = "usd"
  unit_amount = 299000  # $2990.00 (2 months free)
  recurring {
    interval       = "year"
    interval_count = 1
  }
  metadata = {
    plan     = "pro"
    billing  = "annual"
  }
}

resource "stripe_price" "business_monthly" {
  product     = stripe_product.business.id
  currency    = "usd"
  unit_amount = 99900   # $999.00
  recurring {
    interval       = "month"
    interval_count = 1
  }
  metadata = {
    plan     = "business"
    billing  = "monthly"
  }
}

resource "stripe_price" "business_annual" {
  product     = stripe_product.business.id
  currency    = "usd"
  unit_amount = 999000  # $9990.00 (2 months free)
  recurring {
    interval       = "year"
    interval_count = 1
  }
  metadata = {
    plan     = "business"
    billing  = "annual"
  }
}

# ── Webhook endpoint ────────────────────────────────────────────────────────────

resource "stripe_webhook_endpoint" "app" {
  url    = "${var.app_url}/api/settings/billing/webhook"
  enabled_events = [
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "customer.subscription.trial_will_end",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "invoice.upcoming",
    "checkout.session.completed",
    "checkout.session.expired",
  ]
  description = "dgraph.ai main webhook endpoint"
}

# ── Outputs ─────────────────────────────────────────────────────────────────────

output "stripe_price_pro_monthly"      { value = stripe_price.pro_monthly.id }
output "stripe_price_pro_annual"       { value = stripe_price.pro_annual.id }
output "stripe_price_business_monthly" { value = stripe_price.business_monthly.id }
output "stripe_price_business_annual"  { value = stripe_price.business_annual.id }
output "stripe_webhook_secret"         { value = stripe_webhook_endpoint.app.secret; sensitive = true }
output "stripe_webhook_id"             { value = stripe_webhook_endpoint.app.id }

output "env_vars" {
  description = "Paste into .env file"
  sensitive   = true
  value = <<-EOT
    STRIPE_PRICE_PRO=${stripe_price.pro_monthly.id}
    STRIPE_PRICE_PRO_ANNUAL=${stripe_price.pro_annual.id}
    STRIPE_PRICE_BUSINESS=${stripe_price.business_monthly.id}
    STRIPE_PRICE_BUSINESS_ANNUAL=${stripe_price.business_annual.id}
    STRIPE_WEBHOOK_SECRET=${stripe_webhook_endpoint.app.secret}
  EOT
}
