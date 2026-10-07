import uuid
import pytest
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

def test_create_user_success():
    random_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "name": "Zaid Ansari",
        "email": random_email,
        "password": "securepassword123"
    }
    response = client.post("/api/v1/users", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["email"] == payload["email"]
    assert "password_hash" not in data

# --- Phase 3 & 10: Authentication & Workflow Tests ---

def test_auth_workflow():
    unique_email = f"tester_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPassword123!"

    # Register
    reg_res = client.post("/api/v1/auth/register", json={
        "name": "Test User",
        "email": unique_email,
        "password": password
    })
    assert reg_res.status_code == 201

    # Login
    login_res = client.post("/api/v1/auth/login", json={
        "email": unique_email,
        "password": password
    })
    assert login_res.status_code == 200
    token = login_res.json().get("access_token")
    assert token is not None

def test_unsupported_file_upload_rejected():
    # Register and login a user for uploading
    unique_email = f"upload_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "Password123!"
    client.post("/api/v1/auth/register", json={"name": "Uploader", "email": unique_email, "password": password})
    
    login_res = client.post("/api/v1/auth/login", json={"email": unique_email, "password": password})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Attempt uploading an invalid .exe file type
    files = {"file": ("malicious.exe", b"binarycontent", "application/octet-stream")}
    res = client.post("/api/v1/documents/upload", headers=headers, files=files)
    assert res.status_code == 400
    assert "Unsupported file type" in res.json()["detail"]

def test_access_control_isolation():
    email_a = f"usera_{uuid.uuid4().hex[:8]}@example.com"
    email_b = f"userb_{uuid.uuid4().hex[:8]}@example.com"

    client.post("/api/v1/auth/register", json={"name": "User A", "email": email_a, "password": "Password123!"})
    client.post("/api/v1/auth/register", json={"name": "User B", "email": email_b, "password": "Password123!"})

    token_a = client.post("/api/v1/auth/login", json={"email": email_a, "password": "Password123!"}).json()["access_token"]
    token_b = client.post("/api/v1/auth/login", json={"email": email_b, "password": "Password123!"}).json()["access_token"]

    # User A creates a conversation
    conv_a = client.post("/api/v1/conversations", headers={"Authorization": f"Bearer {token_a}"}, json={"title": "Private Conv"}).json()
    conv_id = conv_a["id"]

    # User B attempts to access User A's conversation -> Must be 404 (Tenant Isolation enforced)
    res_b = client.get(f"/api/v1/conversations/{conv_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 404