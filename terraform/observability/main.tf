# Observability plane: where telemetry lands.
#
#   OTel Collector (runs as a sidecar/service) -> Amazon Managed Prometheus
#   Application logs -> CloudWatch log group
#
# The trace backend (Tempo vs FirnTel) is the second deliberate fork and is a
# Phase 2 decision; it is not created here. Grafana points at the Prometheus
# workspace below to graph request rate, latency, and eval-gate recall over time.

variable "project" {
  description = "Project name prefix."
  type        = string
}

variable "environment" {
  description = "Deploy environment label."
  type        = string
}

locals {
  name = "${var.project}-${var.environment}"
}

resource "aws_cloudwatch_log_group" "api" {
  # checkov:skip=CKV_AWS_338:1-year retention is a cost/compliance decision deferred past the reference deployment.
  # checkov:skip=CKV_AWS_158:A dedicated CMK for log groups is Phase 2 hardening; default encryption applies today.
  name              = "/${local.name}/retrieval-api"
  retention_in_days = 30
}

resource "aws_prometheus_workspace" "this" {
  alias = local.name
}

output "log_group_name" {
  description = "CloudWatch log group for retrieval-api."
  value       = aws_cloudwatch_log_group.api.name
}

output "prometheus_endpoint" {
  description = "AMP remote-write endpoint."
  value       = aws_prometheus_workspace.this.prometheus_endpoint
}
