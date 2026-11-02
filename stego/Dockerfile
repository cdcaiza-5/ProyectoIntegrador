FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# El volumen stego_storage hereda este dueño al inicializarse,
# así el proceso no necesita root para escribir en cuarentena.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /var/stego \
    && chown -R appuser:appuser /app /var/stego
USER appuser

EXPOSE 8081

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${STEGO_HTTP_PORT:-8081}"]
