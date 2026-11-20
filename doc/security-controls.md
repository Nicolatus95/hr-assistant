# Controles de seguridad

| Control | Dónde está en el código | Cómo se comprueba |
| --- | --- | --- |
| Validación de la entrada: pregunta vacía o larga, mensaje de historial largo, demasiados mensajes (`422`) | `app/main.py`, función `prepare_inputs`; `MAX_QUESTION_CHARS` y `MAX_HISTORY_ITEMS` en `app/config.py` | `security.feature`, escenarios «history message that is too long» y «Too many history messages» |
| Validación de la salida: HTML y secretos se bloquean, el largo se recorta | `app/output_guard.py`, función `check_output`; se llama en `app/orchestrator.py`, método `_secure`, después del especialista | `test_output_with_html_or_a_secret_is_blocked`, `test_long_output_is_cut_and_ends_with_an_ellipsis`, escenario «An answer with HTML is blocked and audited» |
| Salida mostrada como texto, nunca como HTML | `app/static/index.html` (`textContent`) | `tests/test_static_page.py` |
| Secretos fuera de log, traza, error y código | `app/config.py` (`repr=False`), `app/auth.py`, `app/output_guard.py`, `app/tracing.py` | `test_security_events_are_audited_without_the_key`, `test_gateway_failures_do_not_leak_tokens`, `test_trace_has_the_agent_tree_and_the_metadata` |
| Claves comparadas en tiempo constante | `app/auth.py`, función `authenticate` (`hmac.compare_digest`) | `production.feature`, escenario de clave equivocada |
| Autenticación por `X-API-Key` en `POST /ask` y `GET /metrics` | `app/main.py`, dependencia `require_client` | `production.feature`, escenarios `401` |
| Límite de peticiones por cliente | `app/ratelimit.py`; `app/main.py`, dependencia `limit_client` | escenarios `429` y `test_security_events_are_audited_without_the_key` |
| PII enmascarada antes del supervisor, del modelo, del log y de la traza, y en la respuesta | `app/pii.py`, función `mask`; `app/main.py` (`prepare_inputs`); `app/orchestrator.py` (`_secure`) | `test_card_needs_luhn_and_ids_or_dates_are_not_pii`, `test_pii_is_masked_in_order_without_double_counting`, escenario «A CURP in the question is masked and never logged», `test_trace_has_the_agent_tree_and_the_metadata` |
| `pii_types` en la respuesta y aviso en la página | `app/main.py` (`AskResponse`); `app/static/index.html` (`pii-notice`) | `security.feature`; prueba de la página |
| Auditoría sin valores: `agent_selected`, `tool_call`, `pii_detected`, `output_blocked`, `auth_failed`, `rate_limited` | `app/orchestrator.py`, `app/main.py` (`build_guards`, `build_agents`) | `test_security_events_are_audited_without_the_key` y los escenarios de `security.feature` |
| Mínimo privilegio: cada especialista solo ve sus herramientas; una ajena es `error: unknown tool` y se audita | `app/agent.py` (`directory_tools`, `policies_tools`, `Agent._execute`); `app/main.py` (`build_agents`) | `tests/test_multiagent_units.py` |
| Supervisor con reglas en código (sin tokens ni decisión del modelo) | `app/supervisor.py` | `tests/test_multiagent_units.py` |
| Encabezados de seguridad y `Cache-Control: no-store` en `POST /ask` | `app/main.py`, middleware `observe` (`SECURITY_HEADERS`) | escenario «Every response carries the security headers» |
| Métricas de negocio: peticiones y costo por agente, PII, salidas bloqueadas | `app/metrics.py`, método `record_answer` | escenario «The business metrics count requests per specialist» |
| Trazas por agente sin texto, PII ni claves; error marcado en `502` | `app/tracing.py`, `app/orchestrator.py` | `tests/test_tracing_units.py` |
| Compliance al arrancar en producción | `app/compliance.py`, función `enforce` | `doc/compliance-checklist.md` |
| Servidor sin encabezado `Server` | `Dockerfile` (`--no-server-header`), a cargo de `deploy` | `verification production` |
