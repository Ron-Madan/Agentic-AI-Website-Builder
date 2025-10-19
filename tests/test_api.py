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