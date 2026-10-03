<#
    Despliegue de assistant_base_01 en GCP Cloud Run (Windows - PowerShell)

    Requisitos previos:
      - gcloud ya autenticado (gcloud auth login) y con permisos.
      - Docker Desktop instalado y corriendo.

    Pasos:
      1. Construye la imagen Docker.
      2. La sube (push) al Artifact Registry de GCP.
      3. Despliega en Cloud Run con las variables del .env.

    Uso:
      powershell -ExecutionPolicy Bypass -File .\deploy.ps1
#>

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Variables de configuracion (edita segun tu entorno)
# ---------------------------------------------------------------------------
$Region     = "us-central1"          # Region de GCP
$Repository = "agentic-ai"           # Nombre del repositorio en Artifact Registry
$Service    = "assistant-base-01"    # Nombre del servicio (y de la imagen)
$ProjectId  = "mi-proyecto-gcp"      # ID del proyecto de GCP

# Version generada segun el dia y la hora: YYYYMMDD-HHMMSS
$Version = Get-Date -Format "yyyyMMdd-HHmmss"

# ---------------------------------------------------------------------------
# Rutas (el .env y el Dockerfile estan en la carpeta padre de \scripts)
# ---------------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir   = Split-Path -Parent $ScriptDir
$EnvFile   = Join-Path $RootDir ".env"

$Image       = "$Region-docker.pkg.dev/$ProjectId/$Repository/$Service"
$ImageTag    = "${Image}:${Version}"
$ImageLatest = "${Image}:latest"

Write-Host "=============================================================="
Write-Host " Proyecto     : $ProjectId"
Write-Host " Region       : $Region"
Write-Host " Repositorio  : $Repository"
Write-Host " Servicio     : $Service"
Write-Host " Version      : $Version"
Write-Host " Imagen       : $ImageTag"
Write-Host "=============================================================="

# ---------------------------------------------------------------------------
# 0. Configurar proyecto, habilitar APIs y auth de Docker
# ---------------------------------------------------------------------------
gcloud config set project $ProjectId

# Habilitar APIs necesarias (idempotente). Sin esto, la primera vez el push falla.
Write-Host ">> Habilitando APIs (Artifact Registry y Cloud Run)..."
gcloud services enable artifactregistry.googleapis.com run.googleapis.com

# Auth de Docker contra el Artifact Registry de la region.
gcloud auth configure-docker "$Region-docker.pkg.dev" --quiet

# Crear el repositorio en Artifact Registry si no existe (primera vez).
Write-Host ">> Verificando repositorio '$Repository' en Artifact Registry..."
gcloud artifacts repositories describe $Repository --location $Region *> $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host ">> El repositorio no existe. Creandolo..."
    gcloud artifacts repositories create $Repository `
        --repository-format=docker `
        --location $Region `
        --description "Imagenes de $Service"
} else {
    Write-Host ">> El repositorio ya existe."
}

# ---------------------------------------------------------------------------
# 1. Construir la imagen Docker
# ---------------------------------------------------------------------------
Write-Host ">> Construyendo imagen Docker..."
docker build -t $ImageTag -t $ImageLatest $RootDir

# ---------------------------------------------------------------------------
# 2. Push al Artifact Registry
# ---------------------------------------------------------------------------
Write-Host ">> Subiendo imagen al Artifact Registry..."
docker push $ImageTag
docker push $ImageLatest

# ---------------------------------------------------------------------------
# 3. Leer el .env y generar un archivo YAML de env vars para Cloud Run
#    Se usa --env-vars-file (YAML) para soportar valores con caracteres
#    especiales (@, :, /, &, =, comas) sin romper el parseo.
# ---------------------------------------------------------------------------
if (-not (Test-Path $EnvFile)) {
    Write-Error "No se encontro el archivo .env en $EnvFile"
    exit 1
}

Write-Host ">> Leyendo variables de entorno desde $EnvFile..."
$EnvYaml = [System.IO.Path]::GetTempFileName()
$lines = @()
foreach ($rawLine in Get-Content $EnvFile) {
    $line = $rawLine.Trim()
    if ([string]::IsNullOrWhiteSpace($line)) { continue }   # saltar vacios
    if ($line.StartsWith("#")) { continue }                 # saltar comentarios
    $idx = $line.IndexOf("=")
    if ($idx -lt 1) { continue }                            # debe tener clave
    $key = $line.Substring(0, $idx).Trim()
    $val = $line.Substring($idx + 1).Trim()
    # quitar comillas envolventes si existen
    if (($val.StartsWith('"') -and $val.EndsWith('"')) -or
        ($val.StartsWith("'") -and $val.EndsWith("'"))) {
        $val = $val.Substring(1, $val.Length - 2)
    }
    # YAML entre comillas simples; se escapa la comilla simple duplicandola
    $val = $val.Replace("'", "''")
    $lines += "${key}: '$val'"
}
Set-Content -Path $EnvYaml -Value $lines -Encoding UTF8

# ---------------------------------------------------------------------------
# 4. Desplegar en Cloud Run
# ---------------------------------------------------------------------------
try {
    Write-Host ">> Desplegando en Cloud Run..."
    gcloud run deploy $Service `
        --image $ImageTag `
        --region $Region `
        --platform managed `
        --allow-unauthenticated `
        --port 8080 `
        --env-vars-file $EnvYaml
}
finally {
    Remove-Item -Path $EnvYaml -ErrorAction SilentlyContinue
}

Write-Host "=============================================================="
Write-Host " Despliegue completado: $Service ($Version)"
Write-Host "=============================================================="
