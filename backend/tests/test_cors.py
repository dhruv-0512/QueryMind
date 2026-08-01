import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_cors_preflight_vercel_production():
    response = client.options(
        "/auth/register",
        headers={
            "Origin": "https://query-mind-brown.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type, authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://query-mind-brown.vercel.app"
    assert response.headers.get("access-control-allow-credentials") == "true"
    allowed_methods = response.headers.get("access-control-allow-methods", "")
    for method in ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"]:
        assert method in allowed_methods

def test_cors_preflight_vercel_preview():
    response = client.options(
        "/auth/register",
        headers={
            "Origin": "https://querymind-preview-xyz.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://querymind-preview-xyz.vercel.app"
    assert response.headers.get("access-control-allow-credentials") == "true"

def test_cors_preflight_localhost_3000():
    response = client.options(
        "/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

def test_cors_preflight_localhost_5173():
    response = client.options(
        "/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"

def test_cors_actual_request_health():
    response = client.get(
        "/health",
        headers={
            "Origin": "https://query-mind-brown.vercel.app",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://query-mind-brown.vercel.app"
    assert response.json() == {"status": "healthy"}
