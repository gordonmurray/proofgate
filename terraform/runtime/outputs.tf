output "alb_dns_name" {
  description = "Public DNS name of the ALB."
  value       = aws_lb.this.dns_name
}

output "corpus_bucket" {
  description = "S3 bucket backing Firn's corpus."
  value       = aws_s3_bucket.corpus.id
}

output "cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "task_role_arn" {
  description = "IAM role assumed by the retrieval-api task."
  value       = aws_iam_role.task.arn
}
