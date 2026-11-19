variable "project_id" {
  description = "GCP project shared with the hurricane warehouse"
  type        = string
  default     = "antilles-hurricanes"
}

variable "region" {
  description = "Cloud Run and Artifact Registry region (near Neon's AWS us-east-1)"
  type        = string
  default     = "us-east4"
}

variable "github_repository" {
  description = "The only repository allowed to deploy"
  type        = string
  default     = "tomtessondev/antilles-weather-api"
}
