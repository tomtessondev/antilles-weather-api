# The GCP side of the API: the image registry, the database URL secret, the Cloud Run
# service, and keyless deploys from GitHub Actions. It shares the warehouse's project (and
# so its budget and alerts) and its Workload Identity pool, with its own provider.

terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0, < 8.0"
    }
  }
  backend "gcs" {
    bucket = "antilles-hurricanes-tfstate"
    prefix = "weather-api"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "this" {}

resource "google_project_service" "apis" {
  for_each           = toset(["run.googleapis.com", "artifactregistry.googleapis.com", "secretmanager.googleapis.com"])
  service            = each.key
  disable_on_destroy = false
}

# Images: only the two latest are kept (each is about 370 MB; 0.5 GB is free).
resource "google_artifact_registry_repository" "api" {
  repository_id = "weather-api"
  location      = var.region
  format        = "DOCKER"
  cleanup_policies {
    id     = "keep-two-latest"
    action = "KEEP"
    most_recent_versions {
      keep_count = 2
    }
  }
  cleanup_policies {
    id     = "delete-the-rest"
    action = "DELETE"
    condition {
      tag_state = "ANY"
    }
  }
  depends_on = [google_project_service.apis]
}

# The Neon connection string. Its value is added by hand (gcloud), never in Terraform state.
resource "google_secret_manager_secret" "database_url" {
  secret_id = "weather-api-database-url"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

# The service runs as an account that can read that secret and nothing else.
resource "google_service_account" "runtime" {
  account_id   = "weather-api"
  display_name = "Weather API (Cloud Run runtime)"
}

resource "google_secret_manager_secret_iam_member" "runtime_reads_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service" "api" {
  name                = "weather-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.runtime.email
    scaling {
      min_instance_count = 0 # scale to zero: no request, no cost
      max_instance_count = 2
    }
    containers {
      # The first deploy from GitHub Actions replaces this placeholder.
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true # CPU billed only while a request is served
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
  depends_on = [google_secret_manager_secret_iam_member.runtime_reads_url]
}

# A public API: anyone may reach it; the application checks the API key.
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# GitHub Actions deploys as this account, through the existing pool, with its own provider
# that only trusts this repository.
resource "google_service_account" "deployer" {
  account_id   = "api-deployer"
  display_name = "Weather API deploys (GitHub Actions)"
}

resource "google_project_iam_member" "deployer_runs" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_artifact_registry_repository_iam_member" "deployer_pushes" {
  repository = google_artifact_registry_repository.api.name
  location   = var.region
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_acts_as_runtime" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = "github"
  workload_identity_pool_provider_id = "github-weather-api"
  display_name                       = "GitHub OIDC (weather API)"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  # Only workflows of this repository running on main (deploys never run elsewhere).
  attribute_condition = "assertion.repository == '${var.github_repository}' && assertion.ref == 'refs/heads/main'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_deploys" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/projects/${data.google_project.this.number}/locations/global/workloadIdentityPools/github/attribute.repository/${var.github_repository}"
}
