from typing import TypedDict

from langchain_core.tools import tool

from src.utils.logger import get_logger

logger = get_logger(__name__)


class Skill(TypedDict):
    """Skill que se revela al agente de forma progresiva (progressive disclosure)."""

    name: str  # Identificador único de la skill
    description: str  # Descripción breve (1-2 frases) que se muestra al listar
    content: str  # Instrucciones completas que se cargan solo cuando se necesitan


SKILLS: list[Skill] = [
    {
        "name": "ficha_matricula",
        "description": (
            "Procedimiento para registrar la matrícula de un alumno en un programa "
            "de la academia: datos a solicitar, validaciones y formato de la ficha."
        ),
        "content": """# Ficha de matrícula

## Objetivo
Guiar al alumno para completar su ficha de matrícula en un programa de la academia
y entregarle la ficha final para su confirmación.

## Datos obligatorios
| Campo                | Validación                                                   |
|----------------------|--------------------------------------------------------------|
| Nombres              | Texto no vacío                                               |
| Apellidos            | Texto no vacío                                               |
| DNI                  | Exactamente 8 dígitos numéricos                              |
| Fecha de nacimiento  | Formato DD/MM/AAAA; el alumno debe ser mayor de 18 años      |
| Correo electrónico   | Formato válido (usuario@dominio.ext)                         |
| Celular              | 9 dígitos y debe empezar con 9                               |
| Programa             | Debe existir en la oferta de la academia                     |
| Modalidad / horario  | Una de las modalidades u horarios que ofrece el programa     |
| Medio de pago        | Tarjeta, transferencia bancaria o Yape/Plin                  |

## Datos opcionales
- Empresa donde trabaja y cargo
- Cómo se enteró de la academia

## Pasos
1. Saluda y explica brevemente qué datos se necesitan.
2. Pide los datos que falten de forma conversacional, como máximo 3 o 4 por mensaje.
   Nunca inventes ni supongas datos del alumno.
3. Valida cada dato con las reglas de la tabla. Si alguno es inválido, explica el
   motivo y pídelo de nuevo.
4. Usa la herramienta `retrieve_documents` para confirmar que el programa existe y
   obtener su precio, duración y modalidades u horarios disponibles. Si el programa
   no existe, muestra al alumno las opciones encontradas.
5. Cuando tengas todos los datos obligatorios válidos, muestra la ficha con la
   plantilla de abajo y pide al alumno que confirme si todo es correcto.
6. Si el alumno confirma, indícale que su matrícula quedó registrada y que recibirá
   las instrucciones de pago en su correo. Si pide cambios, corrígelos y vuelve a
   mostrar la ficha.

## Plantilla de la ficha
```
FICHA DE MATRÍCULA
==================
Alumno:              <Nombres> <Apellidos>
DNI:                 <DNI>
Fecha de nacimiento: <DD/MM/AAAA>
Correo:              <correo>
Celular:             <celular>

Programa:            <programa>
Modalidad/horario:   <modalidad u horario>
Duración:            <duración según la base de conocimiento>
Inversión:           <precio según la base de conocimiento>
Medio de pago:       <medio de pago>

Empresa / cargo:     <opcional o "-">
Estado:              PENDIENTE DE CONFIRMACIÓN
```
""",
    },
    {
        "name": "solicitud_certificado",
        "description": (
            "Procedimiento para que un alumno o egresado solicite un certificado de "
            "aprobación o una constancia de estudios: requisitos, datos y formato."
        ),
        "content": """# Solicitud de certificado o constancia de estudios

## Objetivo
Guiar al alumno o egresado para generar su solicitud de certificado o de constancia
de estudios, verificando que cumpla los requisitos.

## Tipos de documento
- **Certificado de aprobación**: solo para alumnos que terminaron y aprobaron el programa.
- **Constancia de estudios**: para alumnos que están cursando un programa actualmente.

## Datos obligatorios
| Campo               | Validación                                                     |
|---------------------|----------------------------------------------------------------|
| Nombres y apellidos | Texto no vacío                                                 |
| DNI                 | Exactamente 8 dígitos numéricos                                |
| Correo electrónico  | Formato válido (usuario@dominio.ext)                           |
| Programa            | Debe existir en la oferta de la academia                       |
| Tipo de documento   | "certificado" o "constancia"                                   |
| Estado del programa | "culminado" (para certificado) o "en curso" (para constancia)  |
| Formato             | "digital" (PDF con firma digital) o "físico" (recojo en sede)  |
| Motivo              | Texto breve (por ejemplo: trabajo, beca, trámite migratorio)   |

## Pasos
1. Pregunta qué tipo de documento necesita, si no lo dijo.
2. Pide los datos que falten de forma conversacional. Nunca inventes datos del alumno.
3. Valida cada dato. Si pide un certificado y su programa sigue en curso, explícale
   que solo puede solicitar una constancia de estudios y ofrécele esa opción.
4. Usa la herramienta `retrieve_documents` para confirmar que el programa existe y
   consultar los requisitos de certificación (nota mínima, asistencia, proyecto
   final). Si la base de conocimiento no tiene esa información, dilo explícitamente.
5. Muestra la solicitud con la plantilla de abajo y pide confirmación.
6. Si el alumno confirma, indícale el plazo de entrega: 5 días hábiles si es digital
   y 10 días hábiles si es físico.

## Plantilla de la solicitud
```
SOLICITUD DE <CERTIFICADO DE APROBACIÓN | CONSTANCIA DE ESTUDIOS>
=================================================================
Solicitante:         <Nombres y apellidos>
DNI:                 <DNI>
Correo:              <correo>

Programa:            <programa>
Estado del programa: <culminado | en curso>
Formato:             <digital | físico>
Motivo:              <motivo>
Plazo estimado:      <5 | 10> días hábiles
Estado:              PENDIENTE DE CONFIRMACIÓN
```
""",
    },
]


@tool
def list_skills() -> str:
    """Lista las skills disponibles (nombre y descripción breve). Úsala para
    descubrir qué procedimientos especializados existen antes de cargar uno."""
    logger.info("Listando %d skill(s)", len(SKILLS))
    return "\n".join(f"- {skill['name']}: {skill['description']}" for skill in SKILLS)


@tool
def load_skill(skill_name: str) -> str:
    """Carga el contenido completo de una skill: instrucciones, validaciones y
    plantillas para atender un tipo de solicitud. Úsala después de list_skills
    con el nombre exacto de la skill (por ejemplo, "ficha_matricula")."""
    for skill in SKILLS:
        if skill["name"] == skill_name:
            logger.info("Skill cargada: %s", skill_name)
            return f"Skill cargada: {skill_name}\n\n{skill['content']}"

    available = ", ".join(skill["name"] for skill in SKILLS)
    logger.warning("Skill no encontrada: %s", skill_name)
    return f"La skill '{skill_name}' no existe. Skills disponibles: {available}"


SKILL_TOOLS = [list_skills, load_skill]
