from pathlib import Path

from src.utils.environment import NEON_PROJECT_ID, PROMPT_VERSION

# Prompts versionados: el texto del system prompt vive en
# prompts/system/{PROMPT_VERSION}.md. Para cambiarlo se crea un archivo nuevo
# (v2.md, ...) y se sube PROMPT_VERSION; el PR dispara el prompt CI (evals).
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "system"

_neon_context = (
    f"Tienes acceso a una base de datos Neon Postgres. "
    f"El project_id que debes usar SIEMPRE en las herramientas MCP es: {NEON_PROJECT_ID}. "
    f"Nunca le preguntes al usuario el project_id, ya lo tienes. "
    f"La base de datos tiene las siguientes tablas: "
    f"- ventas (id, fecha_venta, id_cliente, total_venta, estado (esto puede ser completada o pendiente), id_vendedor)"
    f"- detalle_ventas (id, id_venta, id_producto, cantidad, precio_unitario, subtotal)"
    f"- clientes (id, dni, nombres, sexo, fecha_nacimiento)"
    f"- vendedores (id, dni, nombres, fecha_ingreso, fecha_nacimiento)"
    f"- productos (id, descripcion, precio, stock)"
    f"Cuando el usuario pregunte sobre ventas, clientes, vendedores o productos, usa run_sql con ese project_id para consultar. "
    f"Para preguntas sobre programas, cursos, temarios, precios, duración, requisitos, certificaciones o cualquier "
    f"información institucional, usa retrieve_documents en lugar de run_sql. "
) if NEON_PROJECT_ID else ""



def load_system_prompt(version: str = PROMPT_VERSION) -> str:
    """Carga el system prompt de la versión indicada e inyecta el contexto de Neon."""
    path = PROMPTS_DIR / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"No existe el prompt versionado: {path}")
    template = path.read_text(encoding="utf-8").strip()
    # replace (no format) para que las llaves del markdown no rompan la plantilla.
    return template.replace("{neon_context}", _neon_context).strip()


SYSTEM_PROMPT = load_system_prompt()
