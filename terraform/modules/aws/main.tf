/**
 * AWS test infrastructure for dgraph.ai integration tests.
 *
 * Creates:
 *   - Neo4j community edition on EC2 (t3.medium) — graph backend testing
 *   - S3 bucket — scanner agent S3 connector testing
 *   - SES verified domain — transactional email testing
 *   - IAM roles — IRSA simulation for agent credentials
 *   - Security groups with minimal ingress
 *
 * Cost estimate: ~$30-50/month (t3.medium + storage)
 * Destroy when not testing: terraform destroy
 */

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "environment"          { type = string; default = "dev" }
variable "aws_region"           { type = string; default = "us-east-1" }
variable "neo4j_password"       { type = string; sensitive = true }
variable "neo4j_instance_type"  { type = string; default = "t3.medium" }
variable "vpc_id"               { type = string; default = "" }
variable "subnet_id"            { type = string; default = "" }
variable "allowed_cidr"         { type = string; default = "0.0.0.0/0" }  # restrict in production

data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

# ── Networking ──────────────────────────────────────────────────────────────────

resource "aws_security_group" "neo4j" {
  name        = "dgraphai-neo4j-test-${var.environment}"
  description = "Neo4j test instance for dgraph.ai integration tests"
  vpc_id      = var.vpc_id != "" ? var.vpc_id : null

  # Neo4j Browser
  ingress {
    from_port   = 7474
    to_port     = 7474
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
    description = "Neo4j HTTP browser"
  }

  # Neo4j Bolt
  ingress {
    from_port   = 7687
    to_port     = 7687
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
    description = "Neo4j Bolt protocol"
  }

  # SSH (restrict this in real environments)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
    description = "SSH access"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "dgraphai-neo4j-test-${var.environment}" }
}

# ── Neo4j EC2 instance ──────────────────────────────────────────────────────────

resource "aws_instance" "neo4j" {
  ami                    = data.aws_ami.amazon_linux_2023.id
  instance_type          = var.neo4j_instance_type
  vpc_security_group_ids = [aws_security_group.neo4j.id]
  subnet_id              = var.subnet_id != "" ? var.subnet_id : null

  user_data = base64encode(<<-USERDATA
    #!/bin/bash
    set -ex

    # Install Java 21
    dnf install -y java-21-amazon-corretto

    # Install Neo4j community
    rpm --import https://debian.neo4j.com/neotechnology.gpg.key
    cat > /etc/yum.repos.d/neo4j.repo << 'EOF'
    [neo4j]
    name=Neo4j RPM Repository
    baseurl=https://yum.neo4j.com/stable/5
    enabled=1
    gpgcheck=1
    EOF
    dnf install -y neo4j

    # Configure Neo4j
    sed -i 's/#server.bolt.listen_address=:7687/server.bolt.listen_address=0.0.0.0:7687/' /etc/neo4j/neo4j.conf
    sed -i 's/#server.http.listen_address=:7474/server.http.listen_address=0.0.0.0:7474/' /etc/neo4j/neo4j.conf
    sed -i 's/#dbms.security.auth_enabled=true/dbms.security.auth_enabled=true/' /etc/neo4j/neo4j.conf

    # Set initial password
    neo4j-admin dbms set-initial-password "${var.neo4j_password}"

    # Enable and start
    systemctl enable neo4j
    systemctl start neo4j

    # Install APOC plugin
    NEO4J_HOME=/var/lib/neo4j
    APOC_VERSION=5.18.0
    wget -q "https://github.com/neo4j/apoc/releases/download/$${APOC_VERSION}/apoc-$${APOC_VERSION}-core.jar" \
      -O "$${NEO4J_HOME}/plugins/apoc-$${APOC_VERSION}-core.jar"
    echo "dbms.security.procedures.unrestricted=apoc.*" >> /etc/neo4j/neo4j.conf
    systemctl restart neo4j
    USERDATA
  )

  root_block_device {
    volume_size           = 30
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true
  }

  tags = { Name = "dgraphai-neo4j-test-${var.environment}" }
}

resource "aws_eip" "neo4j" {
  instance = aws_instance.neo4j.id
  domain   = "vpc"
  tags     = { Name = "dgraphai-neo4j-test-${var.environment}" }
}

# ── S3 bucket (scanner agent testing) ──────────────────────────────────────────

resource "aws_s3_bucket" "scanner_test" {
  bucket        = "dgraphai-scanner-test-${var.environment}-${random_id.suffix.hex}"
  force_destroy = true
  tags          = { Purpose = "dgraph.ai scanner connector testing" }
}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_s3_bucket_versioning" "scanner_test" {
  bucket = aws_s3_bucket.scanner_test.id
  versioning_configuration { status = "Enabled" }
}

# Seed with test files
resource "aws_s3_object" "test_video" {
  bucket  = aws_s3_bucket.scanner_test.id
  key     = "media/test-video.mkv"
  content = "fake mkv content for testing"
  content_type = "video/x-matroska"
}

resource "aws_s3_object" "test_document" {
  bucket  = aws_s3_bucket.scanner_test.id
  key     = "documents/test-invoice.pdf"
  content = "fake pdf content for testing"
  content_type = "application/pdf"
}

resource "aws_s3_object" "test_code" {
  bucket  = aws_s3_bucket.scanner_test.id
  key     = "code/config.py"
  content = "# test config\nDEBUG = True\n"
  content_type = "text/x-python"
}

# IAM user for scanner agent (use IRSA in production)
resource "aws_iam_user" "scanner_agent" {
  name = "dgraphai-scanner-agent-${var.environment}"
  tags = { Purpose = "dgraph.ai scanner agent S3 access" }
}

resource "aws_iam_user_policy" "scanner_s3" {
  name = "dgraphai-scanner-s3"
  user = aws_iam_user.scanner_agent.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:ListBucket", "s3:HeadObject"]
      Resource = [
        aws_s3_bucket.scanner_test.arn,
        "${aws_s3_bucket.scanner_test.arn}/*",
      ]
    }]
  })
}

resource "aws_iam_access_key" "scanner_agent" {
  user = aws_iam_user.scanner_agent.name
}

# ── SES (email testing) ─────────────────────────────────────────────────────────

resource "aws_ses_domain_identity" "dgraphai" {
  domain = "dgraph.ai"
}

resource "aws_ses_email_identity" "test" {
  email = "test@dgraph.ai"
}

# ── Outputs ─────────────────────────────────────────────────────────────────────

output "neo4j_public_ip"    { value = aws_eip.neo4j.public_ip }
output "neo4j_bolt_uri"     { value = "bolt://${aws_eip.neo4j.public_ip}:7687" }
output "neo4j_browser_url"  { value = "http://${aws_eip.neo4j.public_ip}:7474" }
output "s3_bucket_name"     { value = aws_s3_bucket.scanner_test.id }
output "s3_bucket_region"   { value = var.aws_region }
output "scanner_access_key" { value = aws_iam_access_key.scanner_agent.id }
output "scanner_secret_key" { value = aws_iam_access_key.scanner_agent.secret; sensitive = true }

output "env_vars" {
  description = "Paste into .env file for integration tests"
  sensitive   = true
  value = <<-EOT
    NEO4J_URI=bolt://${aws_eip.neo4j.public_ip}:7687
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=${var.neo4j_password}
    S3_TEST_BUCKET=${aws_s3_bucket.scanner_test.id}
    S3_TEST_REGION=${var.aws_region}
    AWS_ACCESS_KEY_ID=${aws_iam_access_key.scanner_agent.id}
    AWS_SECRET_ACCESS_KEY=${aws_iam_access_key.scanner_agent.secret}
  EOT
}
