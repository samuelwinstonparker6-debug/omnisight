import pytest
from httpx import ASGITransport, AsyncClient
from backend.main import app

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_webhook_trigger_success(client: AsyncClient):
    """Verifies that the CI/CD webhook accepts payloads and queues the agent."""
    payload = {
        "repository": "infotact/mock-store",
        "branch": "main",
        "commit_sha": "abc123def456",
        "staging_url": "http://localhost:8000/mock-app/index.html"
    }
    
    response = await client.post("/api/v1/webhook/ci-cd-trigger", json=payload)
    
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert "job_id" in data
    assert data["commit_sha"] == "abc123def456"

@pytest.mark.asyncio
async def test_pr_creator_fallback():
    """Verifies PR creator falls back safely when GitHub credentials are omitted."""
    from backend.services.github.pr_creator import create_fix_pr
    
    result = await create_fix_pr(
        file_path="mock-app/styles.css",
        fix_content=".checkout-button { width: 100%; }",
        bug_description="Checkout button overflows on mobile",
    )
    
    assert result["status"] == "success"
    assert "mock" in result["pr_url"]
