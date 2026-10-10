# SLOs del servicio `agent-llmops-obs`

Un **SLO** (Service Level Objective) es un objetivo medible sobre un **SLI**
(Service Level Indicator) en una ventana de tiempo. En un servicio de IA no
basta con "¿está arriba?": la calidad y el costo pueden degradarse sin que el
servicio caiga, así que se miden con el mismo rigor.

> Los valores son ilustrativos para el laboratorio: en un caso real se fijan
> con el negocio y se validan con la prueba de carga (`loadtest/`).

## Objetivos

| SLO | SLI (qué se mide) | Objetivo | Ventana | Fuente | Alerta |
|---|---|---|---|---|---|
| **Disponibilidad** | % de requests a `/api/chat` que no terminan en 5xx ni timeout | ≥ 99.5% | 30 días | Cloud Monitoring: `run.googleapis.com/request_count` por `response_code_class` | Burn rate > 2x en 1 h |
| **Latencia** | p95 de la latencia total de `/api/chat` | < 8 s | 7 días | LangSmith (latencia del trace `chat_request`) o Cloud Monitoring `request_latencies` | p95 > 8 s durante 15 min |
| **Calidad** | % de runs aprobados por la online eval (LLM-as-judge) | ≥ 90% | 7 días | LangSmith: feedback de la regla de online eval | Pass rate < 90% en 24 h |
| **Satisfacción** | % de 👍 sobre el total de feedback (`user_score`) | ≥ 80% | 7 días | LangSmith (`user_score`) y tabla `history.is_ok` | < 80% con al menos 20 votos |
| **Costo** | Costo p95 por request | ≤ $0.01 | 7 días | LangSmith (costo por trace = tokens × precio del modelo) | p95 > $0.01 en 24 h |

**TTFT** (time to first token) no aplica: `/api/chat` no hace streaming y
devuelve la respuesta completa, así que se mide la latencia total.

## Error budget

Con 99.5% de disponibilidad mensual, el presupuesto de error es
**0.5% ≈ 3.6 horas al mes** (o 5 de cada 1000 requests).

Política:

1. **Budget disponible**: se despliegan cambios de prompt y modelo con
   normalidad (siempre pasando el eval gate y el canary).
2. **Budget agotado o burn rate alto**: se **congelan** los cambios de prompt y
   modelo. Solo se despliegan correcciones de confiabilidad hasta recuperar
   el budget.
3. Los SLOs de calidad y costo siguen la misma lógica: si se violan, el
   siguiente cambio de prompt o modelo debe corregirlos antes de agregar
   funcionalidad.

## Dónde se ve cada SLI

- **LangSmith → proyecto `agent-llmops-obs` → Monitor**: latencia p50/p99,
  tokens, costo, tasa de error y feedback (`user_score` y la online eval)
  por día. Filtra por metadata `prompt_version` o `model` para comparar
  versiones.
- **Cloud Run → Métricas**: request count por código, latencias, instancias
  activas, CPU y memoria.
- **Base de datos (`history`)**: feedback y tokens persistidos, útil para
  reportes propios.

```sql
-- Satisfacción y tokens promedio por día (últimos 7 días)
SELECT
    DATE(created_at)                                            AS dia,
    COUNT(*)                                                    AS interacciones,
    COUNT(is_ok)                                                AS con_feedback,
    ROUND(100.0 * AVG(CASE WHEN is_ok THEN 1 ELSE 0 END)
          FILTER (WHERE is_ok IS NOT NULL), 1)                  AS pct_positivo,
    ROUND(AVG(input_tokens))                                    AS avg_input_tokens,
    ROUND(AVG(output_tokens))                                   AS avg_output_tokens
FROM history
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY dia DESC;

-- Respuestas con 👎 para revisar (candidatas al golden set)
SELECT trace_id, question, answer, feedback_comment, feedback_at
FROM history
WHERE is_ok = FALSE
ORDER BY feedback_at DESC
LIMIT 50;
```

## Alertas

- **LangSmith → Alerts** (sobre el proyecto): tasa de errores, latencia y
  promedio de feedback (`user_score`, y la clave de la online eval) con
  umbral y ventana, notificando por webhook o PagerDuty.
- **Cloud Monitoring → SLOs**: crear el SLO de disponibilidad sobre el
  servicio de Cloud Run (*Monitoring → Services → agent-llmops-obs → Create
  SLO*) y una política de alerta por burn rate.

## Autoscaling (Cloud Run)

Definido en `.github/workflows/llmops-cd.yml`:

| Parámetro | Valor | Por qué |
|---|---|---|
| `--concurrency` | 20 | Requests simultáneos por instancia; la mayor parte del tiempo es espera de I/O al LLM |
| `--min-instances` | 0 | Costo cero sin tráfico (subir a 1 para evitar cold starts) |
| `--max-instances` | 5 | Tope de costo; el límite real suele ser la cuota TPM/RPM del proveedor |
| `--memory` | 2Gi | Presidio + spaCy (capa 5 de los guardrails) |

Ajusta estos valores con el punto de saturación que encuentres en la prueba
de carga (`loadtest/README.md`).
