"""Supervisor: elige al especialista con reglas en código, sin llamar al modelo."""

import re

from app.policies import Policies
from app.text import normalize

_EMPLOYEE_ID = re.compile(r"EMP-\d{4}")


def choose_agent(
    question: str, policies: Policies, departments: tuple[str, ...] = ()
) -> tuple[str, str]:
    """Elige al especialista y el motivo.

    Reglas, en orden: id de empleado o departamento (``directory``), palabra
    clave de una política (``policies``) y, si nada coincide, ``directory``.
    Una pregunta que cruza dominios cae en la primera regla que coincida.

    :param question: pregunta ya enmascarada.
    :param policies: políticas, para sus palabras clave.
    :param departments: nombres de departamento conocidos.
    :return: la pareja ``(agente, motivo)``.
    """
    if _EMPLOYEE_ID.search(question):
        return "directory", "employee_id"
    normalized = normalize(question)
    if any(normalize(name) in normalized for name in departments):
        return "directory", "department"
    keyword = policies.find_keyword(question)
    if keyword:
        return "policies", f"policy:{keyword}"
    return "directory", "default"


def choose_tool(
    question: str, reason: str, departments: tuple[str, ...] = ()
) -> tuple[str, dict] | None:
    """Indica la herramienta que el especialista puede traer antes del modelo.

    :param question: pregunta ya enmascarada.
    :param reason: motivo devuelto por :func:`choose_agent`.
    :param departments: nombres de departamento conocidos.
    :return: la pareja ``(herramienta, argumentos)`` o ``None`` si no hay.
    """
    kind, _, keyword = reason.partition(":")
    if kind == "employee_id":
        found = _EMPLOYEE_ID.search(question)
        if found:
            return "get_employee", {"employee_id": found.group()}
    elif kind == "department":
        normalized = normalize(question)
        for name in departments:
            if normalize(name) in normalized:
                return "search_by_department", {"department": name}
    elif kind == "policy" and keyword:
        return "get_policy", {"topic": keyword}
    return None
