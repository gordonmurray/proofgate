# Root outputs: the handful of values a human or the pipeline actually needs.

output "alb_dns_name" {
  description = "Public DNS name of the Application Load Balancer."
  value       = module.runtime.alb_dns_name
}

output "corpus_bucket" {
  description = "S3 bucket backing Firn's corpus objects."
  value       = module.runtime.corpus_bucket
}

output "ecr_repository_url" {
  description = "ECR repository URL for the retrieval-api image."
  value       = module.delivery.ecr_repository_url
}

output "deploy_role_arn" {
  description = "IAM role the GitHub Actions pipeline assumes via OIDC."
  value       = module.delivery.deploy_role_arn
}

output "prometheus_endpoint" {
  description = "Amazon Managed Prometheus remote-write endpoint."
  value       = module.observability.prometheus_endpoint
}
