# Imagen del HR Assistant: Python 3.12 delgado y sin usuario root.
FROM python:3.12-slim

# Sin archivos .pyc y con la salida sin buffer, para ver el log al instante
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Usuario sin privilegios para correr el servicio
RUN useradd --create-home --uid 10001 appuser

# Primero las dependencias: la capa se reutiliza si el código cambia
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# El código y los datos (.dockerignore deja fuera .env, tests y cachés)
COPY --chown=appuser:appuser . .

USER appuser

# Render entrega el puerto en PORT; por omisión 8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
