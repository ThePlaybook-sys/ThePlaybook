from fastapi import FastAPI

app = FastAPI(title="The Playbook — API Gateway")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "api-gateway"}
