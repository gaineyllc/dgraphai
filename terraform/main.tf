/**
 * dgraph.ai Integration Test Infrastructure
 *
 * Provisions everything needed to test:
 *   - Stripe: test mode products + prices + webhook endpoint
 *   - Okta: SCIM app + SAML app + test users/groups
 *   - AWS: Neo4j on EC2, S3 bucket for scanner testing, SES for email
 *   - Azure: Optional CosmosDB Graph for backend testing
 *
 * Usage:
 *   cd terraform/environments/dev
 *   terraform init
 *   terraform plan
 *   terraform apply
 *   terraform output > ../.env.test  (pipe outputs to test env file)
 */

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    stripe = {
      source  = "lukasaron/stripe"
      version = "~> 1.9"
    }
    okta = {
      source  = "okta/okta"
      version = "~> 4.8"
    }
  }

  # State stored in S3 for team sharing
  backend "s3" {
    bucket = "dgraphai-terraform-state"
    key    = "dev/terraform.tfstate"
    region = "us-east-1"
    # encrypt = true  # uncomment once bucket is created
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "dgraphai"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

provider "stripe" {
  api_key = var.stripe_secret_key
}

provider "okta" {
  org_name  = var.okta_org_name
  base_url  = var.okta_base_url
  api_token = var.okta_api_token
}
