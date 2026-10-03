@echo off
REM ===========================================================================
REM  Despliegue de assistant_base_01 en GCP Cloud Run (Windows - CMD / .bat)
REM
REM  Requisitos previos:
REM    - gcloud ya autenticado (gcloud auth login) y con permisos.
REM    - Docker Desktop instalado y corriendo.
REM
REM  Pasos:
REM    1. Construye la imagen Docker.
REM    2. La sube (push) al Artifact Registry de GCP.
REM    3. Despliega en Cloud Run con las variables del .env.
REM ===========================================================================
setlocal EnableDelayedExpansion

REM ---------------------------------------------------------------------------
REM  Variables de configuracion (edita segun tu entorno)
REM ---------------------------------------------------------------------------
set "REGION=us-central1"
set "REPOSITORY=agentic-ai"
set "SERVICE=assistant-base-01"
set "PROJECT_ID=mi-proyecto-gcp"

REM Version segun dia y hora: YYYYMMDD-HHMMSS (independiente del locale via wmic)
for /f %%i in ('wmic os get LocalDateTime ^| findstr "^[0-9]"') do set "LDT=%%i"
set "VERSION=%LDT:~0,8%-%LDT:~8,6%"

REM ---------------------------------------------------------------------------
REM  Rutas (el .env y el Dockerfile estan en la carpeta padre de \scripts)
REM ---------------------------------------------------------------------------
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.."
set "ROOT_DIR=%CD%"
popd
set "ENV_FILE=%ROOT_DIR%\.env"

set "IMAGE=%REGION%-docker.pkg.dev/%PROJECT_ID%/%REPOSITORY%/%SERVICE%"
set "IMAGE_TAG=%IMAGE%:%VERSION%"
set "IMAGE_LATEST=%IMAGE%:latest"

echo ==============================================================
echo  Proyecto     : %PROJECT_ID%
echo  Region       : %REGION%
echo  Repositorio  : %REPOSITORY%
echo  Servicio     : %SERVICE%
echo  Version      : %VERSION%
echo  Imagen       : %IMAGE_TAG%
echo ==============================================================

REM ---------------------------------------------------------------------------
REM  0. Configurar proyecto, habilitar APIs y auth de Docker
REM ---------------------------------------------------------------------------
call gcloud config set project "%PROJECT_ID%" || goto :error

REM Habilitar APIs necesarias (idempotente). Sin esto, la primera vez el push falla.
echo ^>^> Habilitando APIs (Artifact Registry y Cloud Run)...
call gcloud services enable artifactregistry.googleapis.com run.googleapis.com || goto :error

REM Auth de Docker contra el Artifact Registry de la region.
call gcloud auth configure-docker "%REGION%-docker.pkg.dev" --quiet || goto :error

REM Crear el repositorio en Artifact Registry si no existe (primera vez).
echo ^>^> Verificando repositorio "%REPOSITORY%" en Artifact Registry...
call gcloud artifacts repositories describe "%REPOSITORY%" --location "%REGION%" >nul 2>&1
if errorlevel 1 (
  echo ^>^> El repositorio no existe. Creandolo...
  call gcloud artifacts repositories create "%REPOSITORY%" --repository-format=docker --location "%REGION%" --description "Imagenes de %SERVICE%" || goto :error
) else (
  echo ^>^> El repositorio ya existe.
)

REM ---------------------------------------------------------------------------
REM  1. Construir la imagen Docker
REM ---------------------------------------------------------------------------
echo ^>^> Construyendo imagen Docker...
docker build -t "%IMAGE_TAG%" -t "%IMAGE_LATEST%" "%ROOT_DIR%" || goto :error

REM ---------------------------------------------------------------------------
REM  2. Push al Artifact Registry
REM ---------------------------------------------------------------------------
echo ^>^> Subiendo imagen al Artifact Registry...
docker push "%IMAGE_TAG%" || goto :error
docker push "%IMAGE_LATEST%" || goto :error

REM ---------------------------------------------------------------------------
REM  3. Leer el .env y generar un archivo YAML de env vars para Cloud Run
REM     Se usa --env-vars-file (YAML) para soportar valores con caracteres
REM     especiales (@, :, /, &, =, comas) sin romper el parseo.
REM ---------------------------------------------------------------------------
if not exist "%ENV_FILE%" (
  echo ERROR: no se encontro el archivo .env en %ENV_FILE%
  goto :error
)

echo ^>^> Leyendo variables de entorno desde %ENV_FILE%...
set "ENV_YAML=%TEMP%\cloudrun_env_%RANDOM%.yaml"
if exist "%ENV_YAML%" del "%ENV_YAML%"
type nul > "%ENV_YAML%"
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
  set "KEY=%%A"
  set "VAL=%%B"
  REM saltar lineas sin clave
  if not "!KEY!"=="" (
    if not defined VAL (set "VAL=")
    REM YAML entre comillas simples; se escapa la comilla simple duplicandola
    set "VAL=!VAL:'=''!"
    >> "%ENV_YAML%" echo !KEY!: '!VAL!'
  )
)

REM ---------------------------------------------------------------------------
REM  4. Desplegar en Cloud Run
REM ---------------------------------------------------------------------------
echo ^>^> Desplegando en Cloud Run...
call gcloud run deploy "%SERVICE%" ^
  --image "%IMAGE_TAG%" ^
  --region "%REGION%" ^
  --platform managed ^
  --allow-unauthenticated ^
  --port 8080 ^
  --env-vars-file "%ENV_YAML%"
set "DEPLOY_RC=%ERRORLEVEL%"
del "%ENV_YAML%" 2>nul
if not "%DEPLOY_RC%"=="0" goto :error

echo ==============================================================
echo  Despliegue completado: %SERVICE% (%VERSION%)
echo ==============================================================
endlocal
exit /b 0

:error
echo.
echo ERROR: el despliegue fallo. Revisa el mensaje anterior.
endlocal
exit /b 1
