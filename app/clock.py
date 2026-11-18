"""Reloj inyectable para obtener la hora."""

from datetime import datetime, timezone


class SystemClock:
    """Reloj real que devuelve la hora actual en UTC."""

    def now(self) -> datetime:
        """Devuelve la hora actual.

        :return: fecha y hora con zona horaria UTC.
        """
        return datetime.now(timezone.utc)
