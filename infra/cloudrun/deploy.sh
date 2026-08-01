#!/usr/bin/env bash
# Builds the Continuity Room image, pushes it to Artifact Registry, stores
# secrets in Secret Manager, and deploys to Cloud Run.
#
# Review this script before running it — it creates real cloud resources
# (Artifact Registry repo, Secret Manager secrets, a Cloud Run service) and
# incurs cost. Requires the gcloud CLI authenticated against the target
# project, and a repo-root .env populated from .env.example.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy .env.example to .env and fill in real values first." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .env}"
: "${GCP_REGION:?Set GCP_REGION in .env}"
: "${ARTIFACT_REGISTRY_REPO:?Set ARTIFACT_REGISTRY_REPO in .env}"

SERVICE_NAME="continuity-room"
IMAGE="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}/${SERVICE_NAME}:latest"

echo "== Ensuring Artifact Registry repo exists =="
gcloud artifacts repositories describe "$ARTIFACT_REGISTRY_REPO" \
  --project "$GCP_PROJECT_ID" --location "$GCP_REGION" >/dev/null 2>&1 || \
gcloud artifacts repositories create "$ARTIFACT_REGISTRY_REPO" \
  --project "$GCP_PROJECT_ID" --location "$GCP_REGION" \
  --repository-format=docker

echo "== Building and pushing image via Cloud Build =="
gcloud builds submit "$REPO_ROOT" \
  --project "$GCP_PROJECT_ID" \
  --tag "$IMAGE"

# ---------------------------------------------------------------------------
# Secret Manager — every credential lives here, never as a plain Cloud Run
# env var and never hardcoded in this repo.
# ---------------------------------------------------------------------------
create_or_update_secret() {
  local name="$1" value="$2"
  if [[ -z "$value" ]]; then
    echo "Skipping secret '$name': no value set in .env" >&2
    return
  fi
  if gcloud secrets describe "$name" --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    printf '%s' "$value" | gcloud secrets versions add "$name" \
      --project "$GCP_PROJECT_ID" --data-file=-
  else
    printf '%s' "$value" | gcloud secrets create "$name" \
      --project "$GCP_PROJECT_ID" --data-file=- --replication-policy=automatic
  fi
}

echo "== Syncing secrets to Secret Manager =="
create_or_update_secret continuity-room-google-api-key "${GOOGLE_API_KEY:-}"
create_or_update_secret continuity-room-clickhouse-password "${CLICKHOUSE_PASSWORD:-}"
create_or_update_secret continuity-room-grafana-token "${GRAFANA_SERVICE_ACCOUNT_TOKEN:-}"

echo "== Deploying to Cloud Run =="
gcloud run deploy "$SERVICE_NAME" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --image "$IMAGE" \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=${GOOGLE_GENAI_USE_VERTEXAI:-false},GOOGLE_CLOUD_PROJECT=${GCP_PROJECT_ID},GOOGLE_CLOUD_LOCATION=${GOOGLE_CLOUD_LOCATION:-us-central1},GEMINI_MODEL=${GEMINI_MODEL:-gemini-2.5-flash},CLICKHOUSE_HOST=${CLICKHOUSE_HOST},CLICKHOUSE_PORT=${CLICKHOUSE_PORT:-8443},CLICKHOUSE_USER=${CLICKHOUSE_USER:-default},CLICKHOUSE_DATABASE=${CLICKHOUSE_DATABASE:-continuity_room},CLICKHOUSE_SECURE=${CLICKHOUSE_SECURE:-true},GRAFANA_URL=${GRAFANA_URL:-},FRONTEND_ORIGIN=*" \
  --set-secrets "GOOGLE_API_KEY=continuity-room-google-api-key:latest,CLICKHOUSE_PASSWORD=continuity-room-clickhouse-password:latest,GRAFANA_SERVICE_ACCOUNT_TOKEN=continuity-room-grafana-token:latest"

echo "== Done =="
gcloud run services describe "$SERVICE_NAME" \
  --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --format="value(status.url)"
