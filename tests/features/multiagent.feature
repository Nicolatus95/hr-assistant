Feature: Supervisor with two specialists
  A supervisor picks one specialist with rules in code. The directory
  specialist knows the employees and the policies specialist knows the HR
  policies.

  Scenario: An employee question goes to the directory specialist
    When I ask "Who is EMP-0004?"
    Then the response status is 200
    And the specialist is "directory" with the route "employee_id"
    And the answer contains "Jorge"

  Scenario: A vacation question goes to the policies specialist
    When I ask "Cuantos dias de vacaciones tengo?"
    Then the response status is 200
    And the specialist is "policies" with the route "policy:vacaciones"
    And the answer contains "12 días"
    And the tools used are "get_policy"
