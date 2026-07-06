# Three-plane composition (CLAUDE.md > Architecture).
#
#   runtime       the request path: VPC, ALB, ECS Fargate, Firn's S3 bucket
#   delivery      what ships it: ECR + the GitHub OIDC deploy role
#   observability where telemetry lands: Prometheus (AMP) + log group
#
# Each plane is a small module. This root wires them together and passes the
# shared identifiers (VPC, subnets, security groups) between them.

module "runtime" {
  source = "./runtime"

  project         = var.project
  environment     = var.environment
  vpc_cidr        = var.vpc_cidr
  az_count        = var.az_count
  container_image = var.container_image
  container_port  = var.container_port
  desired_count   = var.desired_count
  certificate_arn = var.certificate_arn
  embedder        = var.embedder
  log_group_name  = module.observability.log_group_name
}

module "delivery" {
  source = "./delivery"

  project           = var.project
  environment       = var.environment
  github_repository = var.github_repository
}

module "observability" {
  source = "./observability"

  project     = var.project
  environment = var.environment
}
