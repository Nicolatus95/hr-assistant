Feature: Security of the multi-agent service
  Personal data is masked at the border, input and output are validated,
  every request is audited and the responses carry security headers.

  Scenario: A CURP in the question is masked and never logged
    When I ask "Mi CURP es GARC850101HDFRRL09, quien es EMP-0001?"
    Then the response status is 200
    And the pii types are "CURP"
    And the audit log has a pii_detected event for "question" with types "CURP"
    And the log and the response do not contain "GARC850101HDFRRL09"

  Scenario: A history message that is too long is rejected
    When I ask "Who is EMP-0001?" with a history message of 2001 characters
    Then the response status is 422

  Scenario: Too many history messages are rejected
    When I ask "Who is EMP-0001?" with 21 history messages
    Then the response status is 422

  Scenario: Every response carries the security headers
    When I ask "Who is EMP-0001?"
    Then the response status is 200
    And the security headers are present
    And the response must not be cached
    When I open "/health"
    Then the security headers are present

  Scenario: An answer with HTML is blocked and audited
    Given the model answers "<script>alert(1)</script>"
    When I ask "Who is EMP-0001?"
    Then the response status is 200
    And the answer is the block message
    And the output was blocked
    And the audit log has an output_blocked event with reason "html"
    And the log and the response do not contain "<script>"

  Scenario: The business metrics count requests per specialist
    When I ask "Who is EMP-0001?"
    And I ask "Cuantos dias de vacaciones tengo?"
    And I request the metrics
    Then the requests by agent are "directory" 1 and "policies" 1
    And the metrics include the pii and blocked counters
