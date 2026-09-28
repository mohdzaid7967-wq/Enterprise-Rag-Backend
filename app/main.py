from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="Enterprise Knowledge Assistant",
    version="1.0.0",
    description="Industry-style RAG backend service",
)

# Pydantic schema for validating incoming requests
class EchoRequest(BaseModel):
    message: str

class EchoResponse(BaseModel):
    message: str


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/v1/ping")
def ping():
    return {"ping": "pong"}


@app.post("/api/v1/echo", response_model=EchoResponse)
def echo(payload: EchoRequest):
    return {"message": payload.message}