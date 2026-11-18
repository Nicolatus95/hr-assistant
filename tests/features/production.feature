Feature: Production access control
  The HR Assistant asks for an API key, limits the requests of each client
  and never writes a key in the logs or in an error.

  Scenario: A valid key gets an answer and the log names the client
    Given the service knows the client "ana"
    When client "ana" asks "Who is EMP-0001?"
    Then the response status is 200
    And the request and agent_run log events carry the client "ana"
    And the audit log event carries the client "ana"

  Scenario: Requests without a key are rejected
    Given the service knows the client "ana"
    When I ask "Who is EMP-0001?" without a key
    Then the response status is 401
    And the error detail is "invalid or missing API key"
    When I request the metrics without a key
    Then the response status is 401
    And the error detail is "invalid or missing API key"

  Scenario: A wrong key is rejected
    Given the service knows the client "ana"
    When I ask "Who is EMP-0001?" with the key "not-the-right-key-1234"
    Then the response status is 401
    And the error detail is "invalid or missing API key"

  Scenario: Open endpoints do not need a key
    Given the service knows the client "ana"
    When I open "/" without a key
    Then the response status is 200
    When I open "/health" without a key
    Then the response status is 200
    When I open "/docs" without a key
    Then the response status is 200

  Scenario: Too many requests in a minute are limited until the window passes
    Given the service knows the client "ana"
    And the limit is 2 requests per minute
    When client "ana" asks 3 times
    Then the response status is 429
    And the error detail is "rate limit exceeded"
    And the Retry-After header is between 1 and 60 seconds
    When the clock advances 61 seconds
    And client "ana" asks "Who is EMP-0001?"
    Then the response status is 200

  Scenario: Two clients have separate quotas
    Given the service knows the client "ana"
    And the service knows the client "bob"
    And the limit is 1 requests per minute
    When client "ana" asks 2 times
    Then the response status is 429
    When client "bob" asks 1 times
    Then the response status is 200

  Scenario: The key never appears in the log or in the error
    Given the service knows the client "ana"
    When client "ana" asks "Who is EMP-0001?"
    And I ask "Who is EMP-0001?" with the key "wrong-key-secret-0000"
    Then the log does not contain the key of "ana"
    And the log and the response do not contain "wrong-key-secret-0000"
