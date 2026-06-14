terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = "momentum-dev"
}

#----------------------------------------------------
# 1. S3 Storage Layers (The Zero-Cost Data Lake)
#----------------------------------------------------

# Raw Data Bucket (Stores unparsed feeds directly from ingestion sources)
resource "aws_s3_bucket" "raw_lake" {
  bucket        = "${var.project_prefix}-raw-stage"
  force_destroy = true # Allows clean tear-down during development
}

# Structured Data Bucket (Stores clean, schema-enforced JSON outputs)
resource "aws_s3_bucket" "structured_lake" {
  bucket        = "${var.project_prefix}-structured-stage"
  force_destroy = true
}

# Block all public access by default (Security Best Practice)
resource "aws_s3_bucket_public_access_block" "raw_lock" {
  bucket                  = aws_s3_bucket.raw_lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "structured_lock" {
  bucket                  = aws_s3_bucket.structured_lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

#----------------------------------------------------
# 2. IAM Execution Framework for Week 2 Lambdas
#----------------------------------------------------

# Shared Assume Role Policy Document
data "aws_iam_policy_document" "lambda_assume_logic" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# IAM Execution Role for Lambda
resource "aws_iam_role" "pipeline_lambda_role" {
  name               = "${var.project_prefix}-lambda-execution-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_logic.json
}

# Specific Data Access Policies (Allows reading/writing to our data lake layers)
resource "aws_iam_policy" "lake_access_policy" {
  name        = "${var.project_prefix}-lake-access"
  description = "Provides precise S3 processing permissions to the processing layers"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.raw_lake.arn,
          "${aws_s3_bucket.raw_lake.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.structured_lake.arn,
          "${aws_s3_bucket.structured_lake.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# Attach policy to execution role
resource "aws_iam_role_policy_attachment" "lambda_lake_attach" {
  role       = aws_iam_role.pipeline_lambda_role.name
  policy_arn = aws_iam_policy.lake_access_policy.arn
}
#----------------------------------------------------
# 3. AWS Lambda Deployment & S3 Event Binding
#----------------------------------------------------

# Creates a placeholder ZIP file so Terraform can provision the Lambda resource.
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/lambda_function_payload.zip"
  
  source {
    content  = "def handler(event, context): pass"
    filename = "index.py"
  }
}

resource "aws_lambda_function" "extraction_lambda" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_prefix}-extractor"
  role          = aws_iam_role.pipeline_lambda_role.arn
  handler       = "src.lambda_extraction.handler" # Maps to src/lambda_extraction.py -> handler function
  runtime       = "python3.11"
  timeout       = 30
  memory_size   = 256

  # Injecting production environment variables directly into the cloud runtime
  environment {
    variables = {
      STRUCTURED_BUCKET_NAME = aws_s3_bucket.structured_lake.id
      GROQ_API_KEY           = var.groq_api_key
      GROQ_MODEL             = "llama-3.3-70b-versatile"
    }
  }
}

# Grants S3 explicit permission to invoke this specific Lambda function
resource "aws_lambda_permission" "allow_s3_invocation" {
  statement_id  = "AllowS3ToInvokeLambda"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.extraction_lambda.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.raw_lake.arn
}

# Configures the event notification trigger on the raw landing bucket
resource "aws_s3_bucket_notification" "raw_bucket_notification" {
  bucket = aws_s3_bucket.raw_lake.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.extraction_lambda.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw_source_files/"
    filter_suffix       = ".json"
  }

  depends_on = [aws_lambda_permission.allow_s3_invocation]
}

#----------------------------------------------------
# 4. AWS Glue Data Catalog & Crawler Configuration
#----------------------------------------------------

resource "aws_glue_catalog_database" "lakehouse_db" {
  name         = "${var.project_prefix}_db"
  description  = "Metadata repository for small-cap momentum intelligence"
}

resource "aws_iam_role" "glue_crawler_role" {
  name               = "${var.project_prefix}-glue-crawler-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "glue.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_policy" "glue_crawler_policy" {
  name = "${var.project_prefix}-glue-crawler-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject", "s3:ListBucket"], Resource = [aws_s3_bucket.structured_lake.arn, "${aws_s3_bucket.structured_lake.arn}/*"] },
      { Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], Resource = "arn:aws:logs:*:*:log-group:/aws-lambda/*" },
      { Effect = "Allow", Action = ["glue:UpdateTable", "glue:GetTable", "glue:Tables", "glue:CreateTable"], Resource = ["arn:aws:glue:*:*:catalog", aws_glue_catalog_database.lakehouse_db.arn, "arn:aws:glue:*:*:table/${aws_glue_catalog_database.lakehouse_db.name}/*"] }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "glue_policy_attach" {
  role       = aws_iam_role.glue_crawler_role.name
  policy_arn = aws_iam_policy.glue_crawler_policy.arn
}

resource "aws_glue_crawler" "lakehouse_crawler" {
  database_name = aws_glue_catalog_database.lakehouse_db.name
  name          = "${var.project_prefix}-sentiment-crawler"
  role          = aws_iam_role.glue_crawler_role.arn

  s3_target {
    path = "s3://${aws_s3_bucket.structured_lake.id}/modeled_sentiment/"
  }

  schema_change_policy {
    delete_behavior = "LOG"
    update_behavior = "UPDATE_IN_DATABASE"
  }
}

#----------------------------------------------------
# 5. API Gateway & Serving Lambda
#----------------------------------------------------

# 1. IAM Role to allow the new API Lambda to access Athena and S3
resource "aws_iam_role" "api_lambda_role" {
  name               = "${var.project_prefix}-api-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_policy" "api_athena_policy" {
  name = "${var.project_prefix}-api-athena-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = ["s3:GetBucketLocation", "s3:GetObject", "s3:ListBucket", "s3:PutObject"]
        Resource = [aws_s3_bucket.structured_lake.arn, "${aws_s3_bucket.structured_lake.arn}/*"]
      },
      {
        Effect = "Allow"
        Action = ["glue:GetTable", "glue:GetDatabase"]
        Resource = [
          "arn:aws:glue:*:*:catalog",
          aws_glue_catalog_database.lakehouse_db.arn,
          "arn:aws:glue:*:*:table/${aws_glue_catalog_database.lakehouse_db.name}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:log-group:/aws-lambda/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "api_policy_attach" {
  role       = aws_iam_role.api_lambda_role.name
  policy_arn = aws_iam_policy.api_athena_policy.arn
}

# 2. The Serving Lambda Function
resource "aws_lambda_function" "api_lambda" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_prefix}-api"
  role          = aws_iam_role.api_lambda_role.arn
  handler       = "src.lambda_api.handler" # Maps to src/lambda_api.py -> handler function
  runtime       = "python3.11"
  timeout       = 15
  memory_size   = 256

  environment {
    variables = {
      DATABASE_NAME          = aws_glue_catalog_database.lakehouse_db.name
      ATHENA_OUTPUT_LOCATION = "s3://${aws_s3_bucket.structured_lake.id}/athena_results/"
    }
  }
}

# 3. HTTP API Gateway Configuration
resource "aws_apigatewayv2_api" "momentum_api" {
  name          = "${var.project_prefix}-http-api"
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins = ["*"] # Allows external web applications to request this data
    allow_methods = ["GET"]
  }
}

resource "aws_apigatewayv2_integration" "lambda_integration" {
  api_id             = aws_apigatewayv2_api.momentum_api.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.api_lambda.invoke_arn
  integration_method = "POST"
}

# This defines the exact URL path (e.g., your-api-url.com/sentiment)
resource "aws_apigatewayv2_route" "get_sentiment" {
  api_id    = aws_apigatewayv2_api.momentum_api.id
  route_key = "GET /sentiment"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

resource "aws_apigatewayv2_stage" "api_stage" {
  api_id      = aws_apigatewayv2_api.momentum_api.id
  name        = "$default"
  auto_deploy = true

  # Protects your API from spam (max 10 requests per second)
  default_route_settings {
    throttling_burst_limit = 5
    throttling_rate_limit  = 10
  }
}

# 4. Granting API Gateway Permission to Wake Up the Lambda
resource "aws_lambda_permission" "api_gw_lambda" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.momentum_api.execution_arn}/*/*"
}

# 5. Output the Final Live URL to the Terminal
output "api_endpoint" {
  value       = "${aws_apigatewayv2_api.momentum_api.api_endpoint}/sentiment"
  description = "The live URL for your Momentum Intelligence API"
}

