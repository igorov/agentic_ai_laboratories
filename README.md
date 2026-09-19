# agentic_ai_laboratories

Laboratorios del curso **Agentes de IA**. A lo largo del curso se construyen,
paso a paso, distintos backends que implementan agentes cada vez más
sofisticados. El curso se centra **exclusivamente en el backend**; el frontend
queda fuera del alcance.

---

## Backends del curso

| Carpeta | Descripción | Documentación |
|---------|-------------|---------------|
| [`assistant_base_01`](assistant_base_01/) | Esqueleto base: API REST por capas (FastAPI + SQLAlchemy + PostgreSQL) con chat e historial. Punto de partida del curso. | [README](assistant_base_01/README.md) |


---

## Requisitos generales

- Python 3.11
- Docker (para construir imágenes y desplegar)
- `gcloud` CLI autenticado (para el despliegue en GCP Cloud Run)

Cada backend documenta sus variables de entorno, cómo ejecutarlo localmente y
cómo desplegarlo en su propio README.
