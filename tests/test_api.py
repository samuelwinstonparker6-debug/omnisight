"""
OmniSight — API Endpoint Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tests for the FastAPI health check and API endpoints.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.fixture
async def client():
    """Create an async test client for the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_root(client: AsyncClient):
    """Test root endpoint returns welcome message."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "OmniSight" in data["message"]


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check returns healthy status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "OmniSight"
    assert "version" in data
    assert "checks" in data


@pytest.mark.asyncio
async def test_api_status(client: AsyncClient):
    """Test API v1 status endpoint."""
    response = await client.get("/api/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "services" in data


from unittest.mock import patch

@pytest.mark.asyncio
async def test_scan_success(client: AsyncClient):
    """Test scan endpoint returns success for Day 3."""
    with patch("backend.api.routes.capture_screenshots") as mock_capture:
        with patch("backend.api.routes.analyze_screenshot") as mock_analyze:
            mock_capture.return_value = {"desktop": "/tmp/test.png"}
            mock_analyze.return_value = {
                "status": "success",
                "bugs": [{"id": "1", "title": "Test bug"}]
            }
            response = await client.post("/api/v1/scan")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "screenshots" in data
            assert data["total_bugs"] == 1


@pytest.mark.asyncio
async def test_list_runs_empty(client: AsyncClient):
    """Test list runs endpoint returns correctly."""
    response = await client.get("/api/v1/runs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["runs"], list)
    assert isinstance(data["total"], int)
