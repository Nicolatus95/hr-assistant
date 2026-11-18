"""Reglas de compliance que se aplican al arrancar en producción."""

MIN_KEY_LENGTH = 16


def enforce(config) -> None:
    """Rechaza una configuración insegura cuando ``ENVIRONMENT=production``.

    Los mensajes nombran la regla y, a lo más, el cliente; nunca un valor.

    :param config: configuración ya construida.
    :raises ValueError: con la regla que falla.
    """
    if config.environment != "production":
        return
    if config.model_provider == "fake":
        raise ValueError("production requires MODEL_PROVIDER other than fake")
    if not config.api_keys:
        raise ValueError("production requires API_KEYS with at least one client")
    for name, key in config.api_keys.items():
        if len(key) < MIN_KEY_LENGTH:
            raise ValueError(
                f"production requires API_KEYS keys of {MIN_KEY_LENGTH}+ "
                f"characters; the key of client {name!r} is too short"
            )
    if config.langsmith_tracing and not (config.hide_inputs and config.hide_outputs):
        raise ValueError("production with traces requires HIDE_INPUTS and HIDE_OUTPUTS")
    if config.model_provider == "gateway" and not config.cf_aig_token:
        raise ValueError("production with gateway requires CF_AIG_TOKEN")
