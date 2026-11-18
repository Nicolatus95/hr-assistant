Feature: HR Assistant questions
  HR staff ask about employees and departments through a stateless API.

  Scenario: Asking for an existing employee
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 200
    And the answer mentions "Jorge Díaz"
    And the tools used are "get_employee"

  Scenario: Asking for an unknown employee
    When I ask "¿Quién es EMP-9999?"
    Then the response status is 200
    And the answer says the employee was not found

  Scenario: Asking for a department
    When I ask "¿Quiénes trabajan en Finanzas?"
    Then the response status is 200
    And the answer mentions "Sofía Gómez"
    And the tools used are "search_by_department"

  Scenario: Asking something without an id or a department
    When I ask "Hola, buenos días"
    Then the answer mentions "Pregúntame por un empleado"
    And no tools were used

  Scenario: Rejecting an empty question
    When I ask ""
    Then the response status is 422

  Scenario: Rejecting a question that is too long
    When I ask a question of 2001 characters
    Then the response status is 422

  Scenario: Checking the health of the service
    When I request the health endpoint
    Then the response status is 200
    And the health status is "ok" and it reports a process id

  Scenario: The API keeps no state between requests
    When I ask "¿Quién es EMP-0004?" twice, the second time with a history
    Then both answers are identical

  Scenario: Serving the home page
    When I open the home page
    Then the page contains the test ids "question", "send" and "answer"
