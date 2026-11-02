"""Esqueleto de la actividad 01: solo /health. La actividad 03 lo reemplaza."""

from fastapi import FastAPI

app = FastAPI(title="STEGO", version="0.1.0")


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok", "service": "stego"}
