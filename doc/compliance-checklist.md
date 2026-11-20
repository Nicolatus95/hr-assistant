# Lista de compliance

Reglas que se aplican al arrancar con `ENVIRONMENT=production`. Si una falla, el producto no arranca y el
mensaje nombra la regla, nunca un valor secreto.

| Regla | Dónde está en el código | Cómo se comprueba |
| --- | --- | --- |
| `MODEL_PROVIDER` no puede ser `fake` | `app/compliance.py`, función `enforce` | `test_production_refuses_the_fake_model` |
| `API_KEYS` no puede estar vacía | `app/compliance.py`, función `enforce` | `test_production_*` en `tests/test_production_units.py` y el escenario de arranque de `production.feature` |
| Cada clave tiene 16 caracteres o más | `app/compliance.py`, función `enforce` | `test_production_refuses_a_short_key_without_printing_it` |
| Con trazas encendidas, `HIDE_INPUTS` y `HIDE_OUTPUTS` valen `true` | `app/compliance.py`, función `enforce` | `test_production_refuses_visible_trace_inputs` |
| Con `MODEL_PROVIDER=gateway`, `CF_AIG_TOKEN` no puede estar vacía | `app/compliance.py`, función `enforce` | `test_production_gateway_needs_the_aig_token_and_names_only_the_rule` |
| `POST /ask` y `GET /metrics` exigen `X-API-Key` | `app/main.py`, dependencia `require_client` | `production.feature`, escenarios 401 |
| Las claves se comparan en tiempo constante | `app/auth.py`, función `authenticate` (`hmac.compare_digest`) | `production.feature`, escenario de clave equivocada |
| Una clave mal formada falla diciendo entrada y largo, no el valor | `app/auth.py`, función `parse_api_keys` | `test_malformed_entry_error_shows_its_length_but_not_its_value` |
| Claves y tokens no salen en `repr`, log, traza ni error | `app/config.py` (`repr=False`), `app/logging_setup.py`, `app/llm.py` | `test_new_settings_have_defaults_and_tokens_stay_out_of_repr`, `test_gateway_failures_do_not_leak_tokens` y el escenario «The key never appears in the log or in the error» |
| Límite de peticiones por cliente con reloj inyectado | `app/ratelimit.py`, `app/main.py` (`limit_client`) | `test_requests_over_the_limit_report_the_seconds_left` y los escenarios 429 |
| La página guarda la clave solo en `sessionStorage` | `app/static/index.html` | `tests/test_production_page.py` |
| La PII se enmascara antes del supervisor, del modelo, del log y de la traza | `app/pii.py`, `app/main.py` (`prepare_inputs`) | escenario «A CURP in the question is masked and never logged» |
| La respuesta se valida (HTML, secretos, largo) antes de salir | `app/output_guard.py`, `app/orchestrator.py` (`_secure`) | `test_output_with_html_or_a_secret_is_blocked` |
| La auditoría registra tipos y motivos, nunca valores | `app/orchestrator.py`, `app/main.py` | `test_security_events_are_audited_without_the_key` |
| Toda respuesta lleva encabezados de seguridad | `app/main.py`, middleware `observe` | escenario «Every response carries the security headers» |

El detalle de cada control está en `doc/security-controls.md`.
