"""Unit tests for app.directory."""


def test_employee_is_found_by_id(directory):
    employee = directory.get_employee("EMP-0004")
    assert employee["name"] == "Jorge Díaz"


def test_unknown_employee_is_reported(directory):
    assert not directory.get_employee("EMP-9999")


def test_department_search_ignores_case_and_accents(directory):
    expected = {"Ana López", "Marta Ruiz", "Jorge Díaz"}
    for name in ("Tecnología", "tecnologia"):
        found = {e["name"] for e in directory.search_by_department(name)}
        assert found == expected
    assert not list(directory.search_by_department("Marketing"))
