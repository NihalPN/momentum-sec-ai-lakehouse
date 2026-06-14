output "raw_bucket_name" {
  value       = aws_s3_bucket.raw_lake.id
  description = "Target name for your unstructured data stream ingestion"
}

output "structured_bucket_name" {
  value       = aws_s3_bucket.structured_lake.id
  description = "Target name for your Groq AI model outputs"
}

output "lambda_execution_role_arn" {
  value       = aws_iam_role.pipeline_lambda_role.arn
  description = "The IAM identity resource identifier for your AWS functions"
}