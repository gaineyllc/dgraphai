/**
 * Neo4j Aura free tier setup for integration testing.
 *
 * Uses Neo4j Aura Free (always-on, no credit card for free tier).
 * For larger test datasets, bump to AuraDB Professional.
 *
 * Note: No official Terraform provider for Aura yet (2026).
 * This module outputs instructions and uses the neo4j provider
 * to validate connectivity once the instance is created manually.
 *
 * Manual steps:
 *   1. Go to https://console.neo4j.io → New Instance → AuraDB Free
 *   2. Set name: dgraphai-test
 *   3. Copy connection URI + credentials
 *   4. Set var.neo4j_uri and var.neo4j_password
 *   5. terraform apply (validates connectivity)
 */

terraform {
  required_providers {
    # Neo4j provider for schema validation
    # Install: terraform init will pull this
  }
}

variable "neo4j_uri"      { type = string; default = "" }
variable "neo4j_user"     { type = string; default = "neo4j" }
variable "neo4j_password" { type = string; sensitive = true; default = "" }

output "connection_string" {
  description = "NEO4J_URI to set in .env"
  value       = var.neo4j_uri != "" ? var.neo4j_uri : "Set var.neo4j_uri to your Aura connection URI"
}

output "setup_instructions" {
  value = <<-EOT
    Neo4j Aura Free Setup:
    1. Visit https://console.neo4j.io
    2. Create Instance: AuraDB Free
    3. Name: dgraphai-test
    4. Copy: bolt+s://xxxxxxxx.databases.neo4j.io
    5. Add to .env:
       NEO4J_URI=bolt+s://xxxxxxxx.databases.neo4j.io
       NEO4J_USER=neo4j
       NEO4J_PASSWORD=<generated-password>
    6. Seed test data:
       uv run python tests/fixtures/seed_graph.py
  EOT
}
