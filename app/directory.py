"""Directorio de empleados de solo lectura."""

import json
from pathlib import Path

from app.text import normalize


class Directory:
    """Empleados cargados una sola vez desde un archivo JSON.

    :param path: ruta del archivo ``employees.json``.
    """

    def __init__(self, path) -> None:
        with Path(path).open(encoding="utf-8") as handle:
            self._employees = tuple(json.load(handle))

    @property
    def departments(self) -> tuple[str, ...]:
        """Departamentos existentes, sin repetir."""
        return tuple(dict.fromkeys(e["department"] for e in self._employees))

    def get_employee(self, employee_id: str) -> dict | None:
        """Busca un empleado por id.

        :param employee_id: id con forma ``EMP-0001``.
        :return: una copia del empleado o ``None`` si no existe.
        """
        for employee in self._employees:
            if employee["id"] == employee_id:
                return dict(employee)
        return None

    def search_by_department(self, department: str) -> list[dict]:
        """Lista los empleados de un departamento.

        :param department: nombre, sin distinguir mayúsculas ni acentos.
        :return: lista de empleados, vacía si no hay coincidencias.
        """
        wanted = normalize(department)
        return [
            dict(e) for e in self._employees if normalize(e["department"]) == wanted
        ]
