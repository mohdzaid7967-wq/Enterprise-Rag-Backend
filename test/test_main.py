from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_ping():
    response = client.get("/api/v1/ping")
    assert response.status_code == 200
    assert response.json() == {"ping": "pong"}

def test_echo_endpoint():
    payload = {"message": "hello"}
    response = client.post("/api/v1/echo", json=payload)
    assert response.status_code == 200
    assert response.json() == payload