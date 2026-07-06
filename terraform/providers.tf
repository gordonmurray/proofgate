# AWS provider. Region and default tags come from variables so the same root
# config serves staging and prod, selected by tfvars.

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
