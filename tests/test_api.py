"""Test API endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient):
    """Test the root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "version" in data
    assert "environment" in data


def test_health_check(client: TestClient):
    """Test the health check endpoint."""
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "service" in data


def test_detailed_health_check(client: TestClient):
    """Test the detailed health check endpoint."""
    response = client.get("/health/detailed")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "dependencies" in data


def test_create_project(client: TestClient):
    """Test project creation endpoint."""
    project_data = {
        "description": "Create a portfolio website",
        "requirements": ["About section", "Projects section"],
        "preferences": {"framework": "react"}
    }
    
    response = client.post("/api/v1/projects/", json=project_data)
    assert response.status_code == 200
    data = response.json()
    assert "project_id" in data
    assert data["status"] == "created"


def test_save_and_fetch_code_flow(client: TestClient):
    """End-to-end test for saving code and then fetching it back."""
    # Create project first
    project_data = {
        "description": "Simple site",
        "requirements": [],
        "preferences": {}
    }
    resp = client.post("/api/v1/projects/", json=project_data)
    assert resp.status_code == 200
    project_id = resp.json()["project_id"]

    # Save some code (with markdown fence to test cleaning)
    raw_content = """```html\n<!DOCTYPE html><html><body><h1>Hello</h1></body></html>\n```"""
    put = client.put(f"/api/projects/{project_id}/code", json={
        "html_content": raw_content,
        "message": "test save"
    })
    assert put.status_code == 200
    saved = put.json()
    assert "html_content" in saved
    assert saved["html_content"].startswith("<!DOCTYPE html>") or saved["html_content"].startswith("<html")
    # preview_url may be null in tests if preview manager not running; just ensure key exists
    assert "preview_url" in saved

    # Fetch it back
    get = client.get(f"/api/projects/{project_id}/code")
    assert get.status_code == 200
    got = get.json()
    assert got["html_content"] == saved["html_content"]