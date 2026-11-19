# Infrastructure (GCP)

Terraform for the API's Google Cloud side, in project `antilles-hurricanes` (shared with
the hurricane warehouse: same budget and alerts), region `us-east4`:

- Artifact Registry repository `weather-api` (Docker; only the two latest images are kept);
- Secret Manager secret `weather-api-database-url` (the Neon connection string; its value is
  added by hand, never stored in Terraform state);
- Cloud Run service `weather-api`: scales to zero, at most 2 instances, 1 vCPU, 512 MiB, CPU
  billed only during requests; runs as service account `weather-api`, which can read the
  secret and nothing else; public (`allUsers` invoker), the application checks API keys;
- deploys from GitHub Actions without keys: service account `api-deployer` (Cloud Run
  developer, image pushes, acts as the runtime account) behind a Workload Identity provider
  `github-weather-api`, in the warehouse's `github` pool, trusting only
  `tomtessondev/antilles-weather-api`.

State: `gs://antilles-hurricanes-tfstate`, prefix `weather-api`.

## Once, by hand

```bash
# Neon: create a free project in AWS us-east-1, copy its connection string, then
printf '%s' 'postgresql+psycopg://…' | gcloud secrets versions add weather-api-database-url --data-file=-
```

The secret must have a version before the first `apply` (Cloud Run reads it when the service
is created). The same URL goes into the GitHub secret `DATABASE_URL` (migrations and the
daily load).

## Apply

```bash
terraform init
terraform plan -out=tfplan      # the owner reads it
terraform apply tfplan          # only after the owner approves
terraform output                # deployer account and provider for the GitHub variables
```
