#!/usr/bin/env bash
#
# Configuración inicial (una sola vez) de GCP para el CD con GitHub Actions.
#
# Requisitos previos:
#   - gcloud autenticado (gcloud auth login) con rol Owner o equivalente.
#   - El .env de 06_agent_llmops_obs completo (de ahí se suben los secretos).
#
# Qué hace (idempotente, se puede volver a correr):
#   1. Habilita las APIs necesarias.
#   2. Crea el repositorio de Artifact Registry.
#   3. Crea dos cuentas de servicio:
#        - gh-deployer   → la usa GitHub Actions para desplegar.
#        - agent-runtime → identidad del servicio en Cloud Run (lee secretos).
#   4. Crea el Workload Identity Pool + provider OIDC de GitHub, restringido a
#      tu repositorio: GitHub obtiene credenciales temporales, sin llaves JSON.
#   5. Sube los secretos del .env a Secret Manager.
#   6. Imprime las variables y secretos a cargar en GitHub.
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Variables de configuración  (edita según tu entorno)
# ---------------------------------------------------------------------------
PROJECT_ID="mi-proyecto-gcp"                          # ID del proyecto de GCP
REGION="us-central1"                                  # Región de Cloud Run y Artifact Registry
REPOSITORY="agentic-ai"                               # Repositorio de Artifact Registry
SERVICE="agent-llmops-obs"                            # Servicio de Cloud Run
GITHUB_REPO="igorov/agentic_ai_laboratories"          # owner/repo en GitHub

POOL_ID="github"
PROVIDER_ID="github-oidc"
DEPLOYER_SA_NAME="gh-deployer"
RUNTIME_SA_NAME="agent-runtime"

# Secretos que se suben desde el .env a Secret Manager.
SECRETS=(OPENAI_API_KEY DATABASE_URL QDRANT_URL QDRANT_KEY NEON_API_KEY GROQ_API_KEY LANGSMITH_API_KEY)

# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"

DEPLOYER_SA="${DEPLOYER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "${PROJECT_ID}"
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

# 1. APIs ---------------------------------------------------------------------
echo ">> Habilitando APIs..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  logging.googleapis.com \
  cloudresourcemanager.googleapis.com

# 2. Artifact Registry ----------------------------------------------------------
if ! gcloud artifacts repositories describe "${REPOSITORY}" --location "${REGION}" >/dev/null 2>&1; then
  echo ">> Creando repositorio ${REPOSITORY} en Artifact Registry..."
  gcloud artifacts repositories create "${REPOSITORY}" \
    --repository-format=docker --location "${REGION}" \
    --description "Imágenes de los backends del curso"
fi

# 3. Cuentas de servicio --------------------------------------------------------
create_sa() {
  local name="$1" display="$2"
  if ! gcloud iam service-accounts describe "${name}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1; then
    echo ">> Creando cuenta de servicio ${name}..."
    gcloud iam service-accounts create "${name}" --display-name "${display}"
  fi
}
create_sa "${DEPLOYER_SA_NAME}" "GitHub Actions - deploy Cloud Run"
create_sa "${RUNTIME_SA_NAME}" "Cloud Run runtime - ${SERVICE}"

echo ">> Asignando roles (mínimo privilegio)..."
for role in roles/run.admin roles/artifactregistry.writer roles/logging.viewer; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member "serviceAccount:${DEPLOYER_SA}" --role "${role}" --condition=None >/dev/null
done
# El deployer puede desplegar "actuando como" la cuenta de runtime (solo esa).
gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_SA}" \
  --member "serviceAccount:${DEPLOYER_SA}" --role roles/iam.serviceAccountUser >/dev/null
# El servicio en Cloud Run solo necesita leer los secretos.
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${RUNTIME_SA}" --role roles/secretmanager.secretAccessor --condition=None >/dev/null

# 4. Workload Identity Federation (GitHub OIDC) --------------------------------
if ! gcloud iam workload-identity-pools describe "${POOL_ID}" --location global >/dev/null 2>&1; then
  echo ">> Creando Workload Identity Pool ${POOL_ID}..."
  gcloud iam workload-identity-pools create "${POOL_ID}" \
    --location global --display-name "GitHub Actions"
fi
if ! gcloud iam workload-identity-pools providers describe "${PROVIDER_ID}" \
      --location global --workload-identity-pool "${POOL_ID}" >/dev/null 2>&1; then
  echo ">> Creando provider OIDC ${PROVIDER_ID} (solo ${GITHUB_REPO})..."
  gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_ID}" \
    --location global --workload-identity-pool "${POOL_ID}" \
    --display-name "GitHub OIDC" \
    --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition "assertion.repository == '${GITHUB_REPO}'"
fi
gcloud iam service-accounts add-iam-policy-binding "${DEPLOYER_SA}" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${GITHUB_REPO}" >/dev/null

# 5. Secret Manager ------------------------------------------------------------
read_env() {
  local key="$1" line value
  line="$(grep -E "^${key}=" "${ENV_FILE}" | tail -n 1 || true)"
  value="${line#*=}"
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  printf '%s' "${value}"
}

if [[ -f "${ENV_FILE}" ]]; then
  echo ">> Subiendo secretos desde ${ENV_FILE} a Secret Manager..."
  for key in "${SECRETS[@]}"; do
    value="$(read_env "${key}")"
    if [[ -z "${value}" ]]; then
      echo "   WARN: ${key} está vacío en el .env; no se sube (el CD fallará si lo referencia)."
      continue
    fi
    if gcloud secrets describe "${key}" >/dev/null 2>&1; then
      printf '%s' "${value}" | gcloud secrets versions add "${key}" --data-file=- >/dev/null
      echo "   ${key}: nueva versión"
    else
      printf '%s' "${value}" | gcloud secrets create "${key}" --replication-policy automatic --data-file=- >/dev/null
      echo "   ${key}: creado"
    fi
  done
else
  echo "WARN: no existe ${ENV_FILE}; los secretos no se subieron." >&2
fi

# 6. Resumen para GitHub -------------------------------------------------------
cat <<EOF

==============================================================
 Listo. Carga esto en GitHub → Settings → Secrets and variables → Actions
==============================================================
 Variables (pestaña "Variables"):
   GCP_PROJECT_ID     = ${PROJECT_ID}
   GCP_REGION         = ${REGION}
   GCP_AR_REPOSITORY  = ${REPOSITORY}
   CLOUD_RUN_SERVICE  = ${SERVICE}

 Secrets (pestaña "Secrets"):
   GCP_WORKLOAD_IDENTITY_PROVIDER = projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}
   GCP_DEPLOYER_SA                = ${DEPLOYER_SA}
   GCP_RUNTIME_SA                 = ${RUNTIME_SA}

 Secrets para las evals (prompt CI / model CI), mismos valores que tu .env:
   OPENAI_API_KEY, GROQ_API_KEY, LANGSMITH_API_KEY,
   QDRANT_URL, QDRANT_KEY, QDRANT_COLLECTION_NAME
==============================================================
EOF
