# Provider and Terraform version constraints, plus remote state.
#
# Remote state lives in S3 with native lockfile-based locking (use_lockfile),
# per CLAUDE.md: "Remote state in S3 with locking. No ad-hoc console changes."
# The backend is configured with -backend-config at init time so the bucket name
# is not hard-coded here; CI passes it in. `terraform validate` in CI runs with
# -backend=false, so no real bucket is needed to check syntax.

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.40, < 6.0"
    }
  }

  backend "s3" {
    # Values supplied at init: bucket, key, region.
    # Example:
    #   terraform init \
    #     -backend-config="bucket=proofgate-tfstate-<account>" \
    #     -backend-config="key=runtime/terraform.tfstate" \
    #     -backend-config="region=eu-west-1"
    encrypt      = true
    use_lockfile = true
  }
}
