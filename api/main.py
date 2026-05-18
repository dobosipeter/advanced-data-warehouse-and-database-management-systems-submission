from fastapi import FastAPI

app = FastAPI(
    title="Air Quality Intelligence API",
    description="Operational and analytical API for the air quality intelligence system.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
