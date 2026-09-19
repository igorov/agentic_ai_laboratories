#!/usr/bin/env bash
#
# Despliegue de assistant_base_01 en GCP Cloud Run (Linux / macOS)
#
# Requisitos previos:
#   - gcloud ya autenticado (gcloud auth login) y con permisos.
#   - Docker instalado y corriendo.
#
# Pasos que realiza:
#   1. Construye la imagen Docker.
#   2. La sube (push) al Artifact Registry de GCP.
#   3. Despliega el servicio en Cloud Run tomando las variables del .env.
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Variables de configuracion  (edita segun tu entorno)
# ---------------------------------------------------------------------------
REGION="us-central1"                 # Region de GCP
REPOSITORY="agentic-ai"              # Nombre del repositorio en Artifact Registry
SERVICE="assistant-base-01"          # Nombre del servicio (y de la imagen)
PROJECT_ID="project-effb6f9a-6f21-4320-bf0"         # ID del proyecto de GCP

# Version generada segun el dia y la hora: YYYYMMDD-HHMMSS
VERSION="$(date +%Y%m%d-%H%M%S)"

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"          # carpeta assistant_base_01 (contexto de build)
ENV_FILE="$ROOT_DIR/.env"

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${SERVICE}"
IMAGE_TAG="${IMAGE}:${VERSION}"
IMAGE_LATEST="${IMAGE}:latest"

echo "=============================================================="
echo " Proyecto     : ${PROJECT_ID}"
echo " Region       : ${REGION}"
echo " Repositorio  : ${REPOSITORY}"
echo " Servicio     : ${SERVICE}"
echo " Version      : ${VERSION}"
echo " Imagen       : ${IMAGE_TAG}"
echo "=============================================================="

# ---------------------------------------------------------------------------
# 0. Configurar el proyecto, habilitar APIs y auth de Docker
# ---------------------------------------------------------------------------
gcloud config set project "${PROJECT_ID}"

# Habilitar las APIs necesarias (idempotente). Si es la primera vez, sin esto
# el push a Artifact Registry falla.
echo ">> Habilitando APIs (Artifact Registry y Cloud Run)..."
gcloud services enable artifactregistry.googleapis.com run.googleapis.com

# Auth de Docker contra el Artifact Registry de la region.
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# Crear el repositorio en Artifact Registry si no existe (primera vez).
echo ">> Verificando repositorio '${REPOSITORY}' en Artifact Registry..."
if ! gcloud artifacts repositories describe "${REPOSITORY}" \
      --location "${REGION}" >/dev/null 2>&1; then
  echo ">> El repositorio no existe. Creandolo..."
  gcloud artifacts repositories create "${REPOSITORY}" \
    --repository-format=docker \
    --location "${REGION}" \
    --description "Imagenes de ${SERVICE}"
else
  echo ">> El repositorio ya existe."
fi

# ---------------------------------------------------------------------------
# 1. Construir la imagen Docker
# ---------------------------------------------------------------------------
echo ">> Construyendo imagen Docker..."
docker build -t "${IMAGE_TAG}" -t "${IMAGE_LATEST}" "${ROOT_DIR}"

# ---------------------------------------------------------------------------
# 2. Push al Artifact Registry
# ---------------------------------------------------------------------------
echo ">> Subiendo imagen al Artifact Registry..."
docker push "${IMAGE_TAG}"
docker push "${IMAGE_LATEST}"

# ---------------------------------------------------------------------------
# 3. Leer el .env y generar un archivo YAML de env vars para Cloud Run
#    - Se ignoran lineas vacias y comentarios (#).
#    - Se usa --env-vars-file (YAML) para soportar valores con caracteres
#      especiales (@, :, /, &, =, comas) sin romper el parseo.
# ---------------------------------------------------------------------------
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: no se encontro el archivo .env en ${ENV_FILE}" >&2
  exit 1
fi

echo ">> Leyendo variables de entorno desde ${ENV_FILE}..."
ENV_YAML="$(mktemp)"
trap 'rm -f "${ENV_YAML}"' EXIT

while IFS= read -r line || [[ -n "$line" ]]; do
  # quitar espacios al inicio/final
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  # saltar vacios y comentarios
  [[ -z "$line" || "$line" == \#* ]] && continue
  # debe tener un '='
  [[ "$line" != *"="* ]] && continue
  key="${line%%=*}"
  value="${line#*=}"
  # quitar comillas envolventes si existen
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  # YAML entre comillas simples; se escapa la comilla simple duplicandola
  value="${value//\'/\'\'}"
  printf "%s: '%s'\n" "${key}" "${value}" >> "${ENV_YAML}"
done < "${ENV_FILE}"

# ---------------------------------------------------------------------------
# 4. Desplegar en Cloud Run
# ---------------------------------------------------------------------------
echo ">> Desplegando en Cloud Run..."
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE_TAG}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --env-vars-file "${ENV_YAML}"

echo "=============================================================="
echo " Despliegue completado: ${SERVICE} (${VERSION})"
echo "=============================================================="
