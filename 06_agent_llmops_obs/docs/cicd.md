# CI/CD con GitHub Actions y Cloud Run

Los workflows están en `.github/workflows/` (raíz del repo) y solo se activan
con cambios en `06_agent_llmops_obs/**`.

```
PR ──▶ llmops-ci (lint + pytest)
   └─▶ llmops-prompt-ci (eval gate)    ← solo si cambian prompts/, evals/, config/guardrails/, cloudrun.env.yaml
merge a main ──▶ llmops-ci ──OK──▶ llmops-cd
                                     build → push → deploy sin tráfico (tag canary)
                                     → smoke test → canary 10% (5 min) → 100%
                                                          └─ 5xx > umbral → rollback
manual ──▶ llmops-model-ci (benchmark de otro modelo contra el golden set)
```

| Workflow | Capa (lámina "CI/CD para IA") | Disparador |
|---|---|---|
| `llmops-ci.yml` | Integration CI | PR y push a main |
| `llmops-prompt-ci.yml` | Prompt CI | PR que toca prompts, evals o guardrails |
| `llmops-model-ci.yml` | Model CI | Manual (`workflow_dispatch`, input `model`) |
| `llmops-cd.yml` | CD + canary | `llmops-ci` OK en push a main, o manual |

## Qué necesitas de GCP

No se usa ninguna **llave JSON** de cuenta de servicio. GitHub Actions se
autentica con **Workload Identity Federation**: GitHub emite un token OIDC por
ejecución, GCP lo intercambia por credenciales temporales de la cuenta
`gh-deployer`, y solo lo acepta si viene de tu repositorio.

`scripts/setup_gcp_cicd.sh` crea todo esto (edita las variables del inicio y
córrelo una vez con `gcloud` autenticado como Owner):

| Recurso | Para qué |
|---|---|
| APIs: `run`, `artifactregistry`, `secretmanager`, `iam`, `iamcredentials`, `sts`, `logging` | Despliegue, imágenes, secretos y federación de identidad |
| Artifact Registry `agentic-ai` | Imágenes Docker (tag = commit) |
| SA `gh-deployer` | La usa GitHub Actions. Roles: `run.admin`, `artifactregistry.writer`, `logging.viewer` (leer los 5xx del canary) y `iam.serviceAccountUser` solo sobre `agent-runtime` |
| SA `agent-runtime` | Identidad del servicio en Cloud Run. Rol: `secretmanager.secretAccessor` |
| Workload Identity Pool `github` + provider `github-oidc` | Federación con GitHub, condición `assertion.repository == 'igorov/agentic_ai_laboratories'` |
| Secret Manager | `OPENAI_API_KEY`, `DATABASE_URL`, `QDRANT_URL`, `QDRANT_KEY`, `NEON_API_KEY`, `GROQ_API_KEY`, `LANGSMITH_API_KEY` (los sube el script desde tu `.env`) |

## Qué cargar en GitHub

*Settings → Secrets and variables → Actions*. El script imprime los valores
exactos al terminar.

**Variables**

| Nombre | Ejemplo |
|---|---|
| `GCP_PROJECT_ID` | `mi-proyecto-gcp` |
| `GCP_REGION` | `us-central1` |
| `GCP_AR_REPOSITORY` | `agentic-ai` |
| `CLOUD_RUN_SERVICE` | `agent-llmops-obs` |

**Secrets**

| Nombre | Valor |
|---|---|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/<NÚMERO>/locations/global/workloadIdentityPools/github/providers/github-oidc` |
| `GCP_DEPLOYER_SA` | `gh-deployer@<PROJECT_ID>.iam.gserviceaccount.com` |
| `GCP_RUNTIME_SA` | `agent-runtime@<PROJECT_ID>.iam.gserviceaccount.com` |
| `OPENAI_API_KEY`, `GROQ_API_KEY`, `LANGSMITH_API_KEY`, `QDRANT_URL`, `QDRANT_KEY`, `QDRANT_COLLECTION_NAME` | Los de tu `.env`. Los usan las evals, que ejecutan el agente en el runner |

**Recomendado**

- *Settings → Branches → Branch protection* en `main`: exigir que pasen
  `llmops-ci / test` y `llmops-prompt-ci / eval-gate` antes del merge.
- *Settings → Environments → production*: el CD usa este environment; puedes
  agregar *required reviewers* para aprobar cada despliegue a mano.

## Configuración del servicio

- **Variables no secretas**: `deploy/cloudrun.env.yaml`. Completa
  `QDRANT_COLLECTION_NAME` y `NEON_PROJECT_ID` antes del primer deploy. Cambiar
  `PROMPT_VERSION` u `OPENAI_MODEL` aquí es un cambio revisado por PR que
  dispara el prompt CI.
- **Secretos**: Secret Manager, montados con `--set-secrets` (lista
  `RUNTIME_SECRETS` en `llmops-cd.yml`). Si no usas Neon, quita
  `NEON_API_KEY` de esa lista. Para rotar una llave, vuelve a correr
  `setup_gcp_cicd.sh` (agrega una versión nueva) y redespliega.
- **Autoscaling**: flags `--concurrency`, `--min-instances`,
  `--max-instances`, `--memory` en `llmops-cd.yml` (ver `docs/slos.md`).

## Canary y rollback

1. La revisión nueva se despliega con `--no-traffic --tag canary`: queda
   accesible solo en `https://canary---<servicio>-<hash>.run.app`.
2. `scripts/smoke_test.sh` llama `/health` y tres `/api/chat` (RAG, bloqueo de
   guardrail y saludo) contra esa URL. Si falla, se quita el tag y el job
   falla: **producción nunca recibió tráfico** de esa revisión.
3. Se mueve el `CANARY_PERCENT` (10%) del tráfico a la revisión nueva
   durante `CANARY_MINUTES` (5).
4. Se cuentan los 5xx de la revisión nueva en Cloud Logging. Si superan
   `MAX_5XX` (0), se hace **rollback automático** al 100% de la revisión
   anterior y el job falla. Si no, se promueve al 100%.

**Rollback manual** en cualquier momento:

```bash
gcloud run revisions list --service agent-llmops-obs --region us-central1
gcloud run services update-traffic agent-llmops-obs --region us-central1 \
  --to-revisions <REVISION_ANTERIOR>=100
```

## Notas

- **Primer despliegue**: si el servicio no existe, el CD lo crea directo al
  100% (no hay revisión anterior para hacer canary) y luego corre el smoke
  test.
- **Si antes desplegaste con `scripts/deploy.sh`**: ese script carga las
  llaves como variables de entorno en texto plano. Cloud Run no permite
  convertir una variable existente en secreto con el mismo nombre. Borra el
  servicio una vez (`gcloud run services delete agent-llmops-obs`) antes del
  primer CD, o despliega con otro nombre de servicio.
- `scripts/deploy.sh` sigue sirviendo para despliegues manuales de prueba
  desde tu máquina.
