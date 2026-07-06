# S3 buckets: Firn's corpus objects (the vector store) and the ALB access logs.
# Both are private, encrypted, versioned, and block all public access. There is
# deliberately no cache tier here — caching is internal to Firn (foyer).

data "aws_caller_identity" "current" {}
data "aws_elb_service_account" "main" {}

# ---- Firn corpus bucket ----------------------------------------------------

resource "aws_s3_bucket" "corpus" {
  # checkov:skip=CKV_AWS_144:Cross-region replication is out of scope for a single-region reference deployment.
  # checkov:skip=CKV2_AWS_62:No S3 event consumers in this design; Firn reads objects directly.
  # checkov:skip=CKV_AWS_18:Access logging for the corpus bucket is deferred; not applied here.
  bucket = "${local.name}-corpus-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "corpus" {
  bucket                  = aws_s3_bucket.corpus.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "corpus" {
  bucket = aws_s3_bucket.corpus.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "corpus" {
  bucket = aws_s3_bucket.corpus.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "corpus" {
  bucket = aws_s3_bucket.corpus.id
  rule {
    id     = "expire-noncurrent"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# ---- ALB access-log bucket -------------------------------------------------

resource "aws_s3_bucket" "alb_logs" {
  # checkov:skip=CKV_AWS_145:ALB access logs require SSE-S3 (AES256); ALB cannot deliver to a KMS-CMK bucket.
  # checkov:skip=CKV_AWS_18:This IS the access-log bucket; logging it to itself would be recursive.
  # checkov:skip=CKV_AWS_144:Cross-region replication is out of scope for log data in a reference deployment.
  # checkov:skip=CKV2_AWS_62:Log bucket has no event consumers.
  bucket        = "${local.name}-alb-logs-${data.aws_caller_identity.current.account_id}"
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "alb_logs" {
  bucket                  = aws_s3_bucket.alb_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  rule {
    id     = "expire-logs"
    status = "Enabled"
    filter {}
    expiration {
      days = 90
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# ELB in this region delivers access logs to the bucket via this account.
data "aws_iam_policy_document" "alb_logs" {
  statement {
    sid       = "AllowELBLogDelivery"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.alb_logs.arn}/alb/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]
    principals {
      type        = "AWS"
      identifiers = [data.aws_elb_service_account.main.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  policy = data.aws_iam_policy_document.alb_logs.json
}
