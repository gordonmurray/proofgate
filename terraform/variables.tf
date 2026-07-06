# Root input variables. Everything environment-specific is a variable so the
# three-plane composition below is identical across staging and prod.

variable "project" {
  description = "Project name, used as a resource name prefix and tag."
  type        = string
  default     = "proofgate"
}

variable "environment" {
  description = "Deploy environment label (staging or prod)."
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "environment must be 'staging' or 'prod'."
  }
}

variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "eu-west-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC (a /16 leaves headroom for growth)."
  type        = string
  default     = "10.20.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to spread subnets across."
  type        = number
  default     = 3
}

variable "container_image" {
  description = "Full image reference for retrieval-api (repo:tag or repo@digest)."
  type        = string
  default     = "retrieval-api:latest"
}

variable "container_port" {
  description = "Port the retrieval-api container listens on."
  type        = number
  default     = 8080
}

variable "desired_count" {
  description = "Number of retrieval-api tasks to run."
  type        = number
  default     = 2
}

variable "certificate_arn" {
  description = "ACM certificate ARN for the HTTPS listener. Required before apply."
  type        = string
  default     = ""
}

variable "github_repository" {
  description = "owner/repo allowed to assume the CI deploy role via OIDC."
  type        = string
  default     = "gordonmurray/proofgate"
}

variable "embedder" {
  description = "Embedder fork for the task: 'local' or 'bedrock'. Defaults to 'local'; 'bedrock' is wired in once the Bedrock embedder is implemented."
  type        = string
  default     = "local"

  validation {
    condition     = contains(["local", "bedrock"], var.embedder)
    error_message = "embedder must be 'local' or 'bedrock'."
  }
}
