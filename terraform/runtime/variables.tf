variable "project" {
  description = "Project name prefix."
  type        = string
}

variable "environment" {
  description = "Deploy environment label."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
}

variable "az_count" {
  description = "Number of availability zones to use."
  type        = number
}

variable "container_image" {
  description = "retrieval-api image reference."
  type        = string
}

variable "container_port" {
  description = "Container listen port."
  type        = number
}

variable "desired_count" {
  description = "Number of tasks to run."
  type        = number
}

variable "certificate_arn" {
  description = "ACM certificate ARN for the HTTPS listener."
  type        = string
}

variable "embedder" {
  description = "Embedder fork passed to the task as PROOFGATE_EMBEDDER."
  type        = string
}

variable "log_group_name" {
  description = "CloudWatch log group the task logs to (from the observability plane)."
  type        = string
}
