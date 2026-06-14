variable "aws_region" {
  description = "The target AWS deployment region"
  type        = string
  default     = "us-east-1"
}

variable "project_prefix" {
  description = "Unique prefix attached to all resources to prevent global S3 naming conflicts"
  type        = string
  default     = "momentum-intel-lakehouse"
}
variable "groq_api_key" {
  description = "Groq API Key token for runtime text inference"
  type        = string
  sensitive   = true
}