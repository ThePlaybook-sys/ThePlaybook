from fastapi import FastAPI

app = FastAPI(title="The Playbook — Sports Intelligence Layer")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "sports-intel-layer"}
