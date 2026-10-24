from fastapi import FastAPI

app = FastAPI(title="lingua-api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
