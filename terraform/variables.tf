variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region for test infrastructure"
  type        = string
  default     = "us-east-1"
}

variable "app_url" {
  description = "dgraph.ai application URL (for webhook endpoints)"
  type        = string
  default     = "https://dev.dgraph.ai"
}

# Stripe
variable "stripe_secret_key" {
  description = "Stripe secret key (test mode: sk_test_...)"
  type        = string
  sensitive   = true
}

# Okta
variable "okta_org_name" {
  description = "Okta organization name (e.g. dev-12345678)"
  type        = string
}

variable "okta_base_url" {
  description = "Okta base URL"
  type        = string
  default     = "oktapreview.com"
}

variable "okta_api_token" {
  description = "Okta API token for provisioning"
  type        = string
  sensitive   = true
}

# Neo4j test instance
variable "neo4j_instance_type" {
  description = "EC2 instance type for Neo4j test instance"
  type        = string
  default     = "t3.medium"
}

variable "neo4j_password" {
  description = "Neo4j admin password for test instance"
  type        = string
  sensitive   = true
  default     = "TestNeo4j2026!"
}

# VPC for test instances
variable "vpc_id" {
  description = "VPC ID to deploy test instances into"
  type        = string
  default     = ""   # will create one if empty
}

variable "subnet_id" {
  description = "Subnet ID for test instances"
  type        = string
  default     = ""
}
