Feature: Observability of the HR Assistant
  Support must be able to tell what happened with any request.

  Scenario: A request id is generated when the client sends none
    When I ask "Who is EMP-0001?"
    Then the response status is 200
    And the header request id equals the body request id

  Scenario: The request id sent by the client is respected
    When I ask "Who is EMP-0001?" with the request id "abc-123"
    Then the header request id is "abc-123"
    And the body request id is "abc-123"

  Scenario: A request produces the request and agent_run events
    When I ask "Who is EMP-0001?"
    Then the log has a "request" event with method, path, status and latency
    And the log has an "agent_run" event with the run counters
    And every log line has ts, service, event and request_id

  Scenario: A tool call produces an audit event
    When I ask "Who is EMP-0001?"
    Then the log has an "audit" event for tool "get_employee" with args

  Scenario: The log never contains the question or the answer
    When I ask "Who is EMP-0001?"
    Then the log does not contain the question text
    And the log does not contain the answer text

  Scenario: An internal failure returns 500 and an error event
    Given the model fails with a secret message
    When I ask "Who is EMP-0001?"
    Then the response status is 500
    And the error body has the detail "internal error" and a request id
    And the log has an "error" event without the secret message

  Scenario: The metrics endpoint has the required shape
    When I ask "Who is EMP-0001?"
    And I request the metrics
    Then the metrics have the required fields
    And the metrics count at least 1 request

  Scenario: The SLO is met when the p95 is under the target
    Given the SLO target is 60000 ms
    When I ask "Who is EMP-0001?"
    And I request the metrics
    Then the SLO is reported as met

  Scenario: The SLO is not met when the p95 reaches the target
    Given the SLO target is 1 ms and the model is slow
    When I ask "Who is EMP-0001?"
    And I request the metrics
    Then the SLO is reported as not met

  Scenario: The product works without a LangSmith key
    Given tracing is enabled but there is no API key
    When I ask "Who is EMP-0001?"
    Then the response status is 200

  Scenario: The page has the element that shows the request id
    When I open the home page
    Then the page contains the test id "request-id"
