# Online evals y feedback loop en LangSmith

Las **offline evals** (`evals/run_evals.py`) validan un cambio antes de
desplegarlo, contra un golden set fijo. Las **online evals** evalúan el
tráfico real ya en producción, de forma asíncrona: no agregan latencia ni
costo a la respuesta del usuario.

Todo se configura en la UI de LangSmith, sin código en el backend. El backend
ya envía lo necesario:

- Cada request es un trace `chat_request`, con `run_id = trace_id` y metadata
  `session_id`, `user`, `prompt_version`, `model` y `app_version`.
- El feedback del usuario (👍/👎) llega como feedback `user_score` (1/0) al
  mismo trace, vía `POST /api/feedback`.

## 1. Regla de online eval (LLM-as-judge sobre una muestra)

1. LangSmith → **Projects** → `agent-llmops-obs` → **Rules** (o *Automations*)
   → **+ Add rule**.
2. **Filter**: `Run name = chat_request` y `Error = false` (solo traces
   completos y sin error).
3. **Sampling rate**: `0.2` (20% del tráfico). Es suficiente para estimar la
   tendencia sin pagar un juez por cada request.
4. **Action**: *Online evaluation* → *LLM-as-judge*:
   - Modelo juez: `gpt-4o-mini` (con su API key cargada en *Secrets* de
     LangSmith).
   - Prompt sugerido (criterio *helpfulness + groundedness*):

     ```text
     Evalúa la respuesta de un asistente de una academia de datos.
     Pregunta: {{input.messages}}
     Respuesta: {{output.messages}}
     Aprueba si la respuesta es útil, está en español, no inventa datos
     de la academia (precios, fechas, sedes) y, si no tiene la información,
     lo dice explícitamente.
     ```

   - Feedback key: `online_quality` (score 0/1).
5. Guardar. Desde ese momento, el 20% de los traces nuevos recibe el feedback
   `online_quality`, que alimenta el **SLO de calidad** (`docs/slos.md`).

## 2. Feedback loop: 👎 → revisión → golden set

1. **+ Add rule** sobre el mismo proyecto.
2. **Filter**: feedback `user_score = 0` (o también `online_quality = 0`).
3. **Sampling rate**: `1.0`.
4. **Action**: *Add to annotation queue* → crear la cola `feedback-negativo`.
5. Revisión humana: en **Annotation Queues** → `feedback-negativo`, revisar
   cada caso, corregir la respuesta esperada y usar **Add to dataset** →
   `agent-llmops-obs-golden`.
6. Llevar esos casos también a `evals/datasets/golden_set.jsonl` (versionado
   en git). El siguiente PR que toque el prompt será evaluado contra ellos.

Así se cierra el ciclo de la sesión: **Monitoring → Development**.

## 3. Dashboards y alertas

- **Monitor** (pestaña del proyecto): gráficas de latencia, tokens, costo,
  errores y feedback (`user_score`, `online_quality`). Agrupar por metadata
  `prompt_version` para comparar versiones del prompt en producción.
- **Threads**: como cada trace lleva `session_id` en su metadata, LangSmith
  agrupa los traces de una misma conversación.
- **Alerts**: crear alertas sobre *Feedback score* (`online_quality` < 0.9,
  `user_score` < 0.8), *Latency* (p95 > 8 s) y *Error rate*.

## 4. PII en los traces

El backend envía los traces con un **anonymizer** (`src/services/tracing.py`)
que reemplaza secretos, emails, tarjetas, RUC, celulares y DNI por
`<SECRET>`, `<EMAIL>`, `<CREDIT_CARD>`, `<RUC>`, `<PHONE>` y `<DNI>` antes de
que salgan del servicio. Los evaluadores online y los anotadores nunca ven
esos datos.
