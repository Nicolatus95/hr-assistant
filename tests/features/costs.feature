Feature: Cost levers of the HR Assistant
  Each answer reports the model that produced it, why it was chosen and
  what it cost.

  Scenario: A short question uses the small model
    Given the assistant runs with the default configuration
    When I ask "Who is EMP-0001?"
    Then the model used is the small model
    And the route is "default"

  Scenario: A question with a comparison keyword uses the large model
    Given the assistant runs with the default configuration
    When I ask "Compara a EMP-0001 con EMP-0002"
    Then the model used is the large model
    And the route is "keyword:compara"

  Scenario: A question longer than the limit uses the large model
    Given the assistant runs with the default configuration
    When I ask a question of 81 characters
    Then the model used is the large model
    And the route is "long_question"

  Scenario: Disabling routing sends every question to the large model
    Given the assistant runs with routing disabled
    When I ask "Who is EMP-0001?"
    Then the model used is the large model
    And the route is "routing_off"

  Scenario: The answer reports its cost and the metrics accumulate it
    Given the assistant runs with the default configuration
    When I ask "Who is EMP-0001?"
    Then the cost of the answer is greater than zero
    And the metrics report the same accumulated cost

  Scenario: A model gateway failure is reported as bad gateway
    Given the model gateway is down
    When I ask "Who is EMP-0001?"
    Then the response status is 502
    And the detail is "model unavailable" with a request id
    And the response does not contain the API token

  Scenario: A cached gateway answer is free
    Given the model gateway answers from its cache
    When I ask "Who is EMP-0001?"
    Then one call is reported as cached
    And the cost of the answer is zero
