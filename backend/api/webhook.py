import hmac
import hashlib
import logging
import uuid
from typing import Optional, Any
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from pydantic import BaseModel

from backend.core.config import get_settings
from backend.services.agent.orchestrator import run_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["ci-cd"])

class CICDTriggerPayload(BaseModel):
    repository: str
    branch: str
    commit_sha: str
    staging_url: Optional[str] = None
    environment: Optional[str] = "staging"

async def verify_github_signature(request: Request, signature: str, secret: str) -> None:
    body = await request.body()
    hash_object = hmac.new(secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")

@router.post("/ci-cd-trigger", status_code=202)
async def ci_cd_trigger(
    payload: CICDTriggerPayload,
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(None)
) -> dict[str, Any]:
    """Receives CI/CD build events and triggers the OmniSight autonomous scan."""
    settings = get_settings()
    
    # Validate webhook signature if configured
    if settings.github_webhook_secret and x_hub_signature_256:
        await verify_github_signature(request, x_hub_signature_256, settings.github_webhook_secret)

    target_url = payload.staging_url or settings.staging_url
    job_id = str(uuid.uuid4())

    logger.info(f"CI/CD Webhook received for commit {payload.commit_sha}. Queuing OmniSight scan on {target_url}")

    # Dispatch the self-healing workflow in the background
    background_tasks.add_task(run_pipeline, target_url=target_url, auto_fix=True, create_pr=True)

    return {
        "status": "accepted",
        "job_id": job_id,
        "commit_sha": payload.commit_sha,
        "message": "OmniSight scan queued successfully."
    }


@router.post("/github-events", status_code=200)
async def github_webhook_events(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256")
) -> dict[str, Any]:
    """
    Receives native GitHub webhook events.
    When a Pull Request is merged ('action': 'closed' and 'merged': true),
    autonomously synchronizes the merged code patches to local deployment files
    and verifies site status.
    """
    settings = get_settings()
    if settings.github_webhook_secret and x_hub_signature_256:
        await verify_github_signature(request, x_hub_signature_256, settings.github_webhook_secret)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    event = (x_github_event or payload.get("event") or "").lower()

    if event == "pull_request":
        action = payload.get("action")
        pr_data = payload.get("pull_request", {})
        is_merged = pr_data.get("merged", False)
        pr_url = pr_data.get("html_url")
        pr_number = pr_data.get("number")
        repo_name = payload.get("repository", {}).get("full_name")

        logger.info(f"GitHub Webhook received: PR #{pr_number} action={action} merged={is_merged}")

        if action == "closed" and is_merged:
            from backend.services.github.pr_creator import sync_merged_pr_changes
            background_tasks.add_task(
                sync_merged_pr_changes,
                run_id="",
                target_url="",
                pr_url=pr_url,
                github_repo=repo_name,
            )
            return {
                "status": "processed",
                "message": f"PR #{pr_number} merged. Initiated automated synchronization.",
                "pr_url": pr_url
            }

    return {"status": "ignored", "event": event}

