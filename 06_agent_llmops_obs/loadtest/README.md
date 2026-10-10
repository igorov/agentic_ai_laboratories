# Prueba de carga (Locust)

Mide cómo se comporta el backend bajo carga concurrente: latencia total
(p50/p95), throughput (req/s), tasa de errores (incluidos los 429 del
proveedor del LLM) y el **punto de saturación**.

> ⚠️ Cada request a `/api/chat` llama al LLM real (OpenAI + Groq para los
> guardrails 7 y 8): la prueba **tiene costo**. Empieza con pocos usuarios.

## Instalación

```bash
pip install -r loadtest/requirements.txt
```

## Ejecución

```bash
URL=https://agent-llmops-obs-xxxx.run.app   # o http://localhost:8080

locust -f loadtest/locustfile.py --host "$URL" \
  -u 10 -r 2 -t 3m --headless \
  --csv loadtest/reports/run --html loadtest/reports/run.html
```

| Flag | Significado |
|---|---|
| `-u` | Usuarios concurrentes |
| `-r` | Usuarios nuevos por segundo (rampa) |
| `-t` | Duración |
| `--csv` / `--html` | Reportes en `loadtest/reports/` (ignorado por git) |

Sin `--headless` se abre la UI web en http://localhost:8089 con gráficas en vivo.

## Qué simula cada usuario

- Preguntas de longitud variable (`questions.json`): cortas, medias, largas y
  un intento de prompt injection (que los guardrails bloquean).
- Conversaciones de 3 turnos con el mismo `session_id`: el historial crece y
  con él los tokens de entrada.
- Un `GET /health` de vez en cuando.
- `user = loadtest-<n>`: en LangSmith, filtra por metadata `user` para ver
  solo estos traces (tokens, costo y latencia por span bajo carga).

## Umbrales (fallan el proceso)

Al terminar, `locustfile.py` sale con **exit code 1** si:

| Variable | Default | Regla |
|---|---|---|
| `LOADTEST_MAX_FAILURE_RATIO` | `0.01` | Más de 1% de requests fallidos |
| `LOADTEST_P95_MS` | `8000` | p95 de `/api/chat` mayor a 8 s (SLO de latencia, ver `docs/slos.md`) |

## Encontrar el punto de saturación

Sube la carga en escalones y anota p95, req/s y errores de cada uno:

```bash
for users in 5 10 20; do
  locust -f loadtest/locustfile.py --host "$URL" -u $users -r 2 -t 3m --headless \
    --csv loadtest/reports/u${users} --html loadtest/reports/u${users}.html
done
```

El punto de saturación es el escalón donde el throughput deja de crecer y el
p95 o los errores se disparan. Con APIs gestionadas, el límite suele ser la
cuota **TPM/RPM** del proveedor (verás 429 → 500 en el backend), no la CPU de
Cloud Run. Con ese dato se ajustan `--concurrency` y `--max-instances` en
`.github/workflows/llmops-cd.yml`.
