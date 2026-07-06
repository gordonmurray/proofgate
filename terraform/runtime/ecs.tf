# ECS Fargate service running retrieval-api in the private subnets. Only the ALB
# security group may reach the container port. The same image runs staging and
# prod; behaviour is driven by the environment block below.

resource "aws_security_group" "tasks" {
  name        = "${local.name}-tasks"
  description = "retrieval-api tasks: ingress only from the ALB."
  vpc_id      = aws_vpc.this.id

  tags = { Name = "${local.name}-tasks" }
}

resource "aws_vpc_security_group_ingress_rule" "tasks_from_alb" {
  security_group_id            = aws_security_group.tasks.id
  description                  = "Container port, only from the ALB security group."
  from_port                    = var.container_port
  to_port                      = var.container_port
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.alb.id
}

resource "aws_vpc_security_group_egress_rule" "tasks_egress" {
  security_group_id = aws_security_group.tasks.id
  description       = "Egress for image pulls, S3, and Bedrock (via NAT)."
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_ecs_cluster" "this" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-retrieval-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "retrieval-api"
      image     = var.container_image
      essential = true
      portMappings = [{
        containerPort = var.container_port
        protocol      = "tcp"
      }]
      # OTEL_EXPORTER_OTLP_ENDPOINT is intentionally unset in Phase 0: the app
      # still creates spans, but there is no collector sidecar to export to yet.
      # It is set once the OTel Collector sidecar lands with the observability wiring.
      environment = [
        { name = "PROOFGATE_ENV", value = var.environment },
        { name = "PROOFGATE_EMBEDDER", value = var.embedder },
        { name = "OTEL_SERVICE_NAME", value = "retrieval-api" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = var.log_group_name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "retrieval-api"
        }
      }
      readonlyRootFilesystem = true
    }
  ])
}

resource "aws_ecs_service" "api" {
  name            = "${local.name}-retrieval-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "retrieval-api"
    container_port   = var.container_port
  }

  depends_on = [aws_lb_listener.https]
}

# Target-tracking autoscaling keeps p99 inside the SLO under load.
resource "aws_appautoscaling_target" "api" {
  max_capacity       = 6
  min_capacity       = var.desired_count
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "${local.name}-cpu-target"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace  = aws_appautoscaling_target.api.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 60
  }
}
