from fastapi import FastAPI

app = FastAPI(title="The Playbook — Background Workers")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "workers"}
