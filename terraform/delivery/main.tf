# Delivery plane: the ECR repository the pipeline pushes to, and the IAM role
# GitHub Actions assumes via OIDC. No long-lived cloud keys live in CI
# (CLAUDE.md > IAM: "the pipeline assumes a scoped deploy role via OIDC").

locals {
  name = "${var.project}-${var.environment}"
}

variable "project" {
  description = "Project name prefix."
  type        = string
}

variable "environment" {
  description = "Deploy environment label."
  type        = string
}

variable "github_repository" {
  description = "owner/repo permitted to assume the deploy role."
  type        = string
}

data "aws_caller_identity" "current" {}

# ---- ECR -------------------------------------------------------------------

resource "aws_ecr_repository" "api" {
  name                 = "${var.project}-retrieval-api"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 20 images."
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 20
      }
      action = { type = "expire" }
    }]
  })
}

# ---- GitHub OIDC deploy role ----------------------------------------------

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Scope the trust to the deploy paths only — the main branch and the
    # staging/prod GitHub environments — not `repo:owner/repo:*`, which would let
    # any workflow on any branch with id-token:write assume the deploy role.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repository}:ref:refs/heads/main",
        "repo:${var.github_repository}:environment:staging",
        "repo:${var.github_repository}:environment:prod",
      ]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "${local.name}-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
}

# Scoped deploy permissions: push images and drive ECS deployments. Kept as a
# managed inline policy so the surface is reviewable in one place.
data "aws_iam_policy_document" "deploy" {
  # checkov:skip=CKV_AWS_111:ecr:GetAuthorizationToken and ecs:UpdateService are not resource-scopable and require "*".
  # checkov:skip=CKV_AWS_356:Same as above — these ECR/ECS actions have no ARN to constrain to.
  statement {
    sid       = "EcrPush"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid    = "EcrRepo"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.api.arn]
  }
  statement {
    sid       = "EcsDeploy"
    effect    = "Allow"
    actions   = ["ecs:UpdateService", "ecs:DescribeServices", "ecs:RegisterTaskDefinition"]
    resources = ["*"]
  }
  # RegisterTaskDefinition must pass the task + execution roles to ECS. Scoped to
  # this project's roles and constrained to the ECS tasks service so it cannot be
  # used to assume unrelated roles.
  statement {
    sid       = "PassTaskRoles"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.project}-*"]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "${local.name}-deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}

# ---- Outputs ---------------------------------------------------------------

output "ecr_repository_url" {
  description = "ECR repository URL for retrieval-api."
  value       = aws_ecr_repository.api.repository_url
}

output "deploy_role_arn" {
  description = "IAM role the pipeline assumes via OIDC."
  value       = aws_iam_role.deploy.arn
}
