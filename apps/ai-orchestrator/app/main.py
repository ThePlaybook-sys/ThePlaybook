from fastapi import FastAPI

app = FastAPI(title="The Playbook — AI Orchestrator")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai-orchestrator"}
