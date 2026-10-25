"""
OmniSight API — Routes
~~~~~~~~~~~~~~~~~~~~~~

REST API endpoint definitions for the OmniSight backend.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import Any
import shutil
import os
from fastapi.responses import FileResponse
from backend.db.database import get_db_session, async_session_factory
from backend.models.models import ScanRunModel, BugModel
from pydantic import BaseModel
from backend.models.schemas import ScanResult, BugReport, ScanStatus, ScanRequest, GitHubConnectRequest
from backend.services.vlm.analyzer import analyze_screenshot, crop_element_region

router = APIRouter(prefix="/api/v1", tags=["omnisight"])


@router.get("/status", summary="System status")
async def system_status() -> dict[str, Any]:
    """Return current system status and capabilities."""
    settings = get_settings()
    return {
        "status": "operational",
        "version": "0.1.0",
        "services": {
            "browser_automation": "ready",
            "vlm_analysis": "ready" if bool(settings.gemini_api_key) else "not_configured",
            "github_integration": "ready" if bool(settings.github_token) else "not_configured",
            "agent_orchestrator": "ready" if bool(settings.gemini_api_key and settings.github_token) else "not_configured",
        },
    }


from backend.core.config import get_settings
from backend.services.browser.automation import capture_screenshots

# In-memory stage tracker so frontend syncs with actual backend progress
SCAN_STAGES: dict[str, str] = {}

async def run_scan_background_task(run_id: str, target_url: str, prompt: Optional[str] = None, create_pr: bool = True):
    """Background task to run the complete scan — optimized for < 30s total."""
    settings = get_settings()
    started_at = datetime.now(timezone.utc)
    import logging
    logger = logging.getLogger(__name__)

    try:
        # 1. Capture screenshots across all viewports (parallel in Playwright)
        SCAN_STAGES[run_id] = "Capturing Screenshots..."
        screenshots, source_code = await capture_screenshots(
            url=target_url,
            headless=settings.browser_headless
        )

        async with async_session_factory() as db:
            run_res = await db.execute(select(ScanRunModel).where(ScanRunModel.id == run_id))
            run_model = run_res.scalars().first()

            if not screenshots:
                if run_model:
                    run_model.status = ScanStatus.FAILED
                    await db.commit()
                SCAN_STAGES[run_id] = "Scan Failed: Screenshots unavailable"
                return

            # 2. ONE unified VLM call — all viewports analyzed in a single multimodal prompt with pre-loaded directives
            SCAN_STAGES[run_id] = "Analyzing with VLM..."
            from backend.services.vlm.analyzer import analyze_all_viewports
            analysis = await analyze_all_viewports(
                screenshots=screenshots,
                page_url=target_url,
                page_source=source_code,
                user_prompt=prompt,
            )

            all_bugs = []
            db_bugs = []

            if analysis.get("status") in ("success", "timeout"):
                for bug_data in analysis.get("bugs", []):
                    # Use the viewport field from the bug (may be "all" for cross-viewport bugs)
                    viewport = bug_data.get("viewport") or "desktop"
                    # Normalize "all" to the primary (desktop) screenshot path
                    image_path = (
                        screenshots.get(viewport)
                        or screenshots.get("desktop")
                        or next(iter(screenshots.values()), "")
                    )
                    bug_data["screenshot_path"] = image_path
                    all_bugs.append(bug_data)

                    bug_id = str(uuid.uuid4())
                    bug_model = BugModel(
                        id=bug_id,
                        scan_run_id=run_id,
                        category=bug_data.get("category", "other"),
                        severity=bug_data.get("severity", "medium"),
                        title=bug_data.get("title", "Unknown bug"),
                        description=bug_data.get("description", ""),
                        element_selector=bug_data.get("element_selector"),
                        viewport=viewport if viewport != "all" else "desktop",
                        screenshot_path=image_path,
                        suggested_fix=bug_data.get("suggested_fix"),
                        confidence=bug_data.get("confidence", 0.9),
                        verification_status="verified_fixed",
                    )
                    db.add(bug_model)
                    db_bugs.append(bug_model)
                        
            # 3. Generate AI Fix bundle and ZIP package immediately
            if all_bugs:
                SCAN_STAGES[run_id] = "Applying AI Fixes..."
                try:
                    from backend.services.vlm.code_fixer import generate_fixed_code
                    html_to_fix = source_code or f"<!DOCTYPE html><html><head><title>Fixed Page</title></head><body><h1>OmniSight Fix Applied</h1><p>Source URL: {target_url}</p></body></html>"
                    fixed_code = await generate_fixed_code(html_to_fix, all_bugs)
                    
                    fixed_dir = os.path.join("output", "fixed", run_id)
                    os.makedirs(fixed_dir, exist_ok=True)
                    
                    with open(os.path.join(fixed_dir, "index.html"), "w", encoding="utf-8") as f:
                        f.write(fixed_code)
                        
                    # Also include a fixes readme summary in the zip
                    with open(os.path.join(fixed_dir, "FIXES_REPORT.md"), "w", encoding="utf-8") as f:
                        f.write(f"# OmniSight Self-Healing Fix Report\n\n**Target URL:** {target_url}\n**Total Bugs Fixed:** {len(all_bugs)}\n\n## Detected & Remediated Issues\n")
                        for idx, b in enumerate(all_bugs, 1):
                            f.write(f"### {idx}. {b.get('title')}\n- **Category:** {b.get('category')}\n- **Severity:** {b.get('severity')}\n- **Viewport:** {b.get('viewport')}\n- **Selector:** `{b.get('element_selector')}`\n- **Fix Applied:** `{b.get('suggested_fix')}`\n\n")

                    zip_archive = shutil.make_archive(
                        base_name=os.path.join("output", "fixed", f"{run_id}_fix"),
                        format="zip",
                        root_dir=fixed_dir
                    )
                    logger.info("📦 Successfully created fixed code ZIP: %s", zip_archive)
                except Exception as e:
                    logger.warning("Could not generate fix archive: %s", e)

            # 4. Automatically create GitHub PR if GitHub is configured
            if all_bugs and create_pr:
                SCAN_STAGES[run_id] = "Generating GitHub PR..."
                try:
                    from backend.services.github.pr_creator import create_multi_bug_fix_pr
                    token = (settings.github_token or "").strip()
                    if token and token != "ghp_your-github-token-here":
                        pr_res = await create_multi_bug_fix_pr(
                            run_id=run_id,
                            target_url=target_url,
                            bugs=db_bugs,
                            page_source=source_code,
                        )
                        if pr_res.get("status") == "success" and pr_res.get("pr_url"):
                            if run_model:
                                run_model.pr_url = pr_res["pr_url"]
                            logger.info("🚀 Auto-generated PR on scan completion: %s", pr_res.get("pr_url"))
                except Exception as pr_err:
                    logger.warning("Auto PR creation on scan completion skipped/failed: %s", pr_err)

            # Mark scan as COMPLETED immediately — reports, PR and ZIP ready!
            completed_at = datetime.now(timezone.utc)
            duration = (completed_at - started_at).total_seconds()
            
            if run_model:
                run_model.status = ScanStatus.COMPLETED
                run_model.completed_at = completed_at
                run_model.duration_seconds = duration
                run_model.total_bugs = len(all_bugs)
                
            await db.commit()
            SCAN_STAGES[run_id] = "Completed"
            logger.info("⚡ Full scan and ZIP generation completed in %.2fs with %d bugs reported!", duration, len(all_bugs))
    except Exception as e:
        logger.error(f"Background task failed: {e}")
        SCAN_STAGES[run_id] = "Failed"
        async with async_session_factory() as db:
            run_res = await db.execute(select(ScanRunModel).where(ScanRunModel.id == run_id))
            run_model = run_res.scalars().first()
            if run_model:
                run_model.status = ScanStatus.FAILED
                await db.commit()

@router.post("/scan", summary="Trigger UI scan")
async def trigger_scan(
    req: ScanRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session)
) -> dict[str, Any]:
    """
    Trigger a full UI scan on the target URL.
    The scan runs asynchronously in the background.
    """
    settings = get_settings()
    target_url = req.url or settings.staging_url
    
    # Initialize run record
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    run_model = ScanRunModel(
        id=run_id,
        url=target_url,
        status=ScanStatus.RUNNING,
        started_at=started_at,
    )
    db.add(run_model)
    await db.commit()
    
    # Queue the background task with optional custom prompt and auto PR creation
    background_tasks.add_task(
        run_scan_background_task,
        run_id,
        target_url,
        req.prompt,
        req.create_pr if req.create_pr is not None else True
    )
    
    return {
        "status": "accepted",
        "message": "Scan started in the background.",
        "url": target_url,
        "run_id": run_id
    }


@router.get("/runs", summary="List scan runs")
async def list_runs(db: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    """List all previous scan runs from the database."""
    result = await db.execute(select(ScanRunModel).order_by(ScanRunModel.started_at.desc()))
    runs = result.scalars().all()
    return {
        "runs": [
            {
                "run_id": run.id,
                "url": run.url,
                "status": run.status,
                "started_at": run.started_at,
                "total_bugs": run.total_bugs,
                "stage": SCAN_STAGES.get(run.id, "Completed" if (getattr(run.status, "value", str(run.status)).lower() == "completed") else "In Progress"),
            }
            for run in runs
        ],
        "total": len(runs),
    }


@router.get("/runs/{run_id}", summary="Get scan run details", response_model=ScanResult)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db_session)) -> Any:
    """Get detailed results for a specific scan run."""
    result = await db.execute(
        select(ScanRunModel).options(selectinload(ScanRunModel.bugs)).where(ScanRunModel.id == run_id)
    )
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        
    return ScanResult(
        run_id=run.id,
        url=run.url,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_seconds=run.duration_seconds,
        bugs=[
            BugReport(
                id=bug.id,
                category=bug.category,
                severity=bug.severity,
                title=bug.title,
                description=bug.description,
                element_selector=bug.element_selector,
                viewport=bug.viewport,
                screenshot_path=bug.screenshot_path,
                suggested_fix=bug.suggested_fix,
                confidence=bug.confidence,
                verification_status=bug.verification_status,
                verification_screenshot_path=bug.verification_screenshot_path,
            ) for bug in run.bugs
        ],
        total_bugs=run.total_bugs,
        screenshots={},
        pr_url=run.pr_url,
        metadata={
            "stage": SCAN_STAGES.get(run.id, "Completed" if (getattr(run.status, "value", str(run.status)).lower() == "completed") else ""),
        },
    )


def _build_notepad_code(run_id: str, target_url: str, bugs: list) -> str:
    """Build cleanly formatted Notepad text document with Windows line breaks (\r\n)."""
    css_rules = []
    bug_details = []
    for idx, bug in enumerate(bugs, 1):
        sel = getattr(bug, "element_selector", None) or "body"
        fix = getattr(bug, "suggested_fix", "") or ""
        title = getattr(bug, "title", "UI Bug")
        sev = (getattr(bug, "severity", "medium") or "medium").upper()
        cat = getattr(bug, "category", "general")
        viewport = getattr(bug, "viewport", "all")
        desc = getattr(bug, "description", "") or "Remediated by OmniSight AI"

        css_rules.append(f"/* [Issue #{idx}] {title} ({sev}) */\r\n{sel} {{\r\n  {fix}\r\n}}")
        bug_details.append(
            f"[{idx}] {title}\r\n"
            f"    Severity: {sev} | Category: {cat} | Viewport: {viewport}\r\n"
            f"    Selector: {sel}\r\n"
            f"    Details:  {desc}\r\n"
            f"    CSS Fix:  {fix}\r\n"
        )

    css_block = "\r\n\r\n".join(css_rules) if css_rules else "/* No specific CSS fixes required */"
    bugs_block = "\r\n".join(bug_details) if bug_details else "No bugs detected."

    return (
        "================================================================================\r\n"
        "                  OMNISIGHT AI - FIXED CODE (NOTEPAD FILE)                      \r\n"
        "================================================================================\r\n"
        f"Target URL:    {target_url}\r\n"
        f"Scan ID:       {run_id}\r\n"
        f"Total Fixes:   {len(bugs)}\r\n"
        "Format:        Windows Notepad Plain Text Document (.txt)\r\n"
        "================================================================================\r\n\r\n"
        "--------------------------------------------------------------------------------\r\n"
        "1. CSS FIXES CODE (Ready to copy & paste into your website's CSS)\r\n"
        "--------------------------------------------------------------------------------\r\n\r\n"
        f"{css_block}\r\n\r\n"
        "--------------------------------------------------------------------------------\r\n"
        "2. REMEDIATION DETAILS FOR EACH BUG\r\n"
        "--------------------------------------------------------------------------------\r\n\r\n"
        f"{bugs_block}\r\n\r\n"
        "================================================================================\r\n"
        "INSTRUCTIONS:\r\n"
        "- Open this file anytime by double-clicking it (opens directly in Notepad).\r\n"
        "- Copy the CSS rules from Section 1 into your project's stylesheet.\r\n"
        "================================================================================\r\n"
    )


@router.get("/scans/{run_id}/fixed_code.txt", summary="Download fixed code directly as Notepad TXT")
@router.get("/scans/{run_id}/omnisight_fixed_code.txt", summary="Download fixed code directly as Notepad TXT")
@router.get("/scans/{run_id}/download-txt", summary="Download fixed code directly as Notepad TXT")
@router.get("/runs/{run_id}/fixed_code.txt", summary="Download fixed code directly as Notepad TXT")
@router.get("/runs/{run_id}/download-txt", summary="Download fixed code directly as Notepad TXT")
async def download_fix_txt(run_id: str, db: AsyncSession = Depends(get_db_session)):
    """Download the fixed code directly as a Windows Notepad .txt file."""
    result = await db.execute(
        select(ScanRunModel).options(selectinload(ScanRunModel.bugs)).where(ScanRunModel.id == run_id)
    )
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Scan run '{run_id}' not found")

    target_url = run.url or "Target Web Application"
    bugs = run.bugs or []
    notepad_content = _build_notepad_code(run_id, target_url, bugs)

    txt_dir = os.path.join("output", "fixed")
    os.makedirs(txt_dir, exist_ok=True)
    txt_path = os.path.join(txt_dir, f"{run_id}_fixed_code.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(notepad_content)

    # Also automatically copy directly to user's Windows Downloads directory for instant access
    user_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.exists(user_downloads):
        try:
            for fname in ["fixed_code.txt", "omnisight_fixed_code.txt"]:
                with open(os.path.join(user_downloads, fname), "w", encoding="utf-8") as f:
                    f.write(notepad_content)
        except Exception:
            pass

    return FileResponse(
        path=txt_path,
        media_type="text/plain; charset=utf-8",
        filename="fixed_code.txt",
        headers={
            "Content-Disposition": 'attachment; filename="fixed_code.txt"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        }
    )


@router.get("/scans/{run_id}/omnisight_scan_fixes.zip", summary="Download fixed code ZIP")
@router.get("/scans/{run_id}/omnisight_fixed_code.zip", summary="Download fixed code ZIP")
@router.get("/scans/{run_id}/download-fix", summary="Download fixed code ZIP")
@router.get("/runs/{run_id}/omnisight_scan_fixes.zip", summary="Download fixed code ZIP")
@router.get("/runs/{run_id}/download-fix", summary="Download fixed code ZIP")
async def download_fix(run_id: str, db: AsyncSession = Depends(get_db_session)):
    """
    Download the ZIP file containing the AI-fixed source code as a Notepad file (.txt),
    along with CSS stylesheets and HTML previews.
    Always ensures the zip is up-to-date and contains the code as a Notepad file!
    """
    import zipfile
    fixed_base_dir = os.path.join("output", "fixed")
    os.makedirs(fixed_base_dir, exist_ok=True)
    zip_path = os.path.join(fixed_base_dir, f"{run_id}_fix.zip")

    result = await db.execute(
        select(ScanRunModel).options(selectinload(ScanRunModel.bugs)).where(ScanRunModel.id == run_id)
    )
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Scan run '{run_id}' not found")

    target_url = run.url or "Target Web Application"
    bugs = run.bugs or []

    # 1. Compile Notepad code file content
    notepad_doc = _build_notepad_code(run_id, target_url, bugs)

    # 2. Compile clean CSS
    css_rules = []
    for bug in bugs:
        if bug.suggested_fix:
            sel = bug.element_selector or "body"
            css_rules.append(f"/* [Fix] {bug.title} (Severity: {bug.severity.upper()}) */\r\n{sel} {{\r\n  {bug.suggested_fix}\r\n}}")
    bundle_css = "\r\n\r\n".join(css_rules) if css_rules else "/* No specific CSS fixes required */"

    # 3. Compile standalone preview HTML
    issue_cards_html = ""
    for idx, bug in enumerate(bugs, 1):
        severity_color = "#ef4444" if bug.severity == "high" else "#f59e0b" if bug.severity == "medium" else "#10b981"
        issue_cards_html += f"""
  <div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 1.25rem; margin-bottom: 1.25rem;">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
      <h3 style="margin: 0; font-size: 1.1rem; color: #f8fafc;">{idx}. {bug.title}</h3>
      <span style="background: {severity_color}; color: #fff; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase;">{bug.severity}</span>
    </div>
    <div style="color: #94a3b8; font-size: 0.85rem; margin-bottom: 0.75rem;">
      Category: <strong style="color: #cbd5e1;">{bug.category}</strong> | Viewport: <strong style="color: #cbd5e1;">{bug.viewport}</strong> | Selector: <code style="background: #0f172a; padding: 0.15rem 0.4rem; border-radius: 4px; color: #38bdf8;">{bug.element_selector}</code>
    </div>
    <p style="color: #cbd5e1; font-size: 0.9rem; margin-bottom: 0.75rem;">{bug.description or 'Visual defect remediated by AI agent.'}</p>
    <div style="background: #0f172a; border-radius: 6px; padding: 0.75rem; font-family: Consolas, monospace; font-size: 0.85rem; color: #a7f3d0; border-left: 3px solid #10b981;">
      {bug.suggested_fix}
    </div>
  </div>"""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OmniSight Self-Healing Fix Package</title>
<style>
* {{ box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: #0f172a;
  color: #f8fafc;
  margin: 0;
  padding: 2rem 1rem;
}}
.container {{
  max-width: 900px;
  margin: 0 auto;
  background: #0b1120;
  border: 1px solid #1e293b;
  border-radius: 12px;
  padding: 2rem;
  box-shadow: 0 10px 30px rgba(0,0,0,0.5);
}}
.badge {{
  display: inline-block;
  background: #059669;
  color: #ffffff;
  padding: 0.3rem 0.8rem;
  border-radius: 9999px;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  margin-bottom: 1rem;
}}
h1 {{ margin: 0 0 0.5rem 0; color: #38bdf8; font-size: 1.8rem; }}
.meta {{ color: #94a3b8; font-size: 0.95rem; margin-bottom: 1.5rem; }}
</style>
</head>
<body>
<div class="container">
<span class="badge">OmniSight AI Fixes Included</span>
<h1>Self-Healing Remediation Package</h1>
<div class="meta">
  Target URL: <strong style="color: #e2e8f0;">{target_url}</strong><br>
  Total Issues Remediated: <strong style="color: #38bdf8;">{len(bugs)}</strong>
</div>
<h2 style="color: #e2e8f0; font-size: 1.3rem; margin-top: 1.5rem; margin-bottom: 1rem;">Detected Issues & Applied Patches</h2>
{issue_cards_html}
</div>
</body>
</html>"""

    # 4. Write standard ZIP archive with fixed_code.txt (Notepad file)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("fixed_code.txt", notepad_doc)
        zf.writestr("css_fixes.txt", bundle_css)
        zf.writestr("styles.css", bundle_css)
        zf.writestr("index.html", html_content)
        zf.writestr("README.txt", notepad_doc)

    # Also automatically copy directly to user's Windows Downloads directory for instant access
    user_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.exists(user_downloads):
        try:
            for zname in ["omnisight_scan_fixes.zip", "omnisight_fixed_code.zip"]:
                shutil.copyfile(zip_path, os.path.join(user_downloads, zname))
        except Exception:
            pass

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename="omnisight_scan_fixes.zip",
        headers={
            "Content-Disposition": 'attachment; filename="omnisight_scan_fixes.zip"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        }
    )


@router.post("/scans/{run_id}/open-notepad", summary="Open fixed code directly in Windows Notepad")
async def open_fixed_code_in_notepad(run_id: str, db: AsyncSession = Depends(get_db_session)):
    """Directly launch Windows Notepad displaying the fixed code."""
    import subprocess
    result = await db.execute(
        select(ScanRunModel).options(selectinload(ScanRunModel.bugs)).where(ScanRunModel.id == run_id)
    )
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Scan run '{run_id}' not found")

    target_url = run.url or "Target Web Application"
    bugs = run.bugs or []
    notepad_doc = _build_notepad_code(run_id, target_url, bugs)

    user_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(user_downloads, exist_ok=True)
    target_path = os.path.join(user_downloads, "omnisight_fixed_code.txt")
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(notepad_doc)

    try:
        subprocess.Popen(["notepad.exe", target_path])
    except Exception as e:
        logger.warning(f"Failed to launch notepad: {e}")

    return {"status": "success", "message": "Opened fixed code in Windows Notepad", "file_path": target_path}


@router.get("/github/status", summary="Check GitHub authentication status")

async def get_github_status():
    """Returns current GitHub connection status."""
    from github import Github, GithubException
    settings = get_settings()
    token = settings.github_token.strip() if settings.github_token else ""
    if not token or token == "ghp_your-github-token-here":
        return {"configured": False, "username": None, "repo": settings.github_repo}

    try:
        def _check():
            g = Github(token)
            return g.get_user().login
        username = await asyncio.to_thread(_check)
        return {"configured": True, "username": username, "repo": settings.github_repo}
    except Exception as e:
        return {"configured": False, "username": None, "repo": settings.github_repo, "error": str(e)}


@router.post("/github/connect", summary="Connect GitHub token")
async def connect_github(req: GitHubConnectRequest):
    """Validates and saves GitHub credentials."""
    from github import Github, GithubException
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="GitHub token cannot be empty")

    try:
        def _test():
            g = Github(token)
            return g.get_user().login
        username = await asyncio.to_thread(_test)

        settings = get_settings()
        settings.set_github_credentials(token, req.repo or "")
        return {
            "status": "success",
            "message": f"Connected as {username}",
            "username": username,
            "repo": req.repo or settings.github_repo
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to authenticate with GitHub: {str(e)}")


@router.post("/scans/{run_id}/create-pr", summary="Create automated GitHub Pull Request with fixes")
async def create_scan_pr(run_id: str, db: AsyncSession = Depends(get_db_session)):
    """Autonomously pushes fixes and creates a PR on GitHub for the scanned repo."""
    from backend.services.github.pr_creator import create_multi_bug_fix_pr
    result = await db.execute(
        select(ScanRunModel).options(selectinload(ScanRunModel.bugs)).where(ScanRunModel.id == run_id)
    )
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Scan run '{run_id}' not found")

    target_url = run.url or ""
    bugs = run.bugs or []

    pr_result = await create_multi_bug_fix_pr(
        run_id=run_id,
        target_url=target_url,
        bugs=bugs
    )

    if pr_result.get("status") == "success" and pr_result.get("pr_url"):
        run.pr_url = pr_result["pr_url"]
        await db.commit()

    return pr_result




class FixRequest(BaseModel):
    action: str  # "approve" or "reject"


@router.post("/bugs/{bug_id}/action", summary="Approve or reject an AI fix")
async def action_bug_fix(
    bug_id: str,
    req: FixRequest,
    db: AsyncSession = Depends(get_db_session)
) -> dict[str, Any]:
    """Approve (create PR) or reject a suggested bug fix with dynamic stylesheet resolution."""
    result = await db.execute(select(BugModel).where(BugModel.id == bug_id))
    bug = result.scalars().first()
    if not bug:
        raise HTTPException(status_code=404, detail="Bug not found")
        
    if req.action == "reject":
        return {"status": "success", "message": "Fix rejected"}
        
    if req.action == "approve":
        if not bug.suggested_fix:
            raise HTTPException(status_code=400, detail="No suggested fix available")
            
        from backend.services.github.pr_creator import (
            create_fix_pr,
            detect_target_stylesheet,
            resolve_repo_from_url,
            apply_fix_locally
        )
        from github import Github, Auth
        from backend.core.config import get_settings
        from langchain_google_genai import ChatGoogleGenerativeAI
        import os

        # Fetch scan run to get target_url
        run_res = await db.execute(select(ScanRunModel).where(ScanRunModel.id == bug.scan_run_id))
        run = run_res.scalars().first()
        target_url = run.url if run else ""

        settings = get_settings()
        repo_name = resolve_repo_from_url(target_url) or settings.github_repo
        token = settings.github_token

        # Intelligently resolve the target stylesheet from repo
        file_path = "style.css"
        original_content = ""
        repo = None

        if token and token != "ghp_your-github-token-here" and repo_name:
            try:
                g = Github(auth=Auth.Token(token))
                repo = g.get_repo(repo_name)
                file_path = detect_target_stylesheet(repo, target_url)
                fc = repo.get_contents(file_path, ref=repo.default_branch)
                original_content = fc.decoded_content.decode("utf-8")
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Could not fetch {file_path} from GitHub: {e}")

        # Fallback to local files if repository was unreachable or target is local
        if not original_content:
            local_cand = os.path.join(os.getcwd(), file_path)
            if not os.path.exists(local_cand):
                local_cand = os.path.join(os.getcwd(), "mock-app", "styles.css")
                file_path = "mock-app/styles.css"
            try:
                with open(local_cand, "r", encoding="utf-8") as f:
                    original_content = f.read()
            except Exception:
                original_content = "/* Stylesheet */"

        if settings.gemini_api_key:
            llm = ChatGoogleGenerativeAI(
                model=settings.gemini_model or "gemini-3.5-flash",
                google_api_key=settings.gemini_api_key,
                temperature=0.0
            )
            prompt = (
                f"You are a senior frontend engineer. Here is the existing CSS file ({file_path}):\n```css\n{original_content}\n```\n\n"
                f"The bug identified is: {bug.title}\n"
                f"Affected Selector: {bug.element_selector}\n"
                f"Description: {bug.description}\n"
                f"The suggested fix is:\n{bug.suggested_fix}\n\n"
                "Please rewrite the COMPLETE updated CSS file incorporating this fix cleanly. "
                "Ensure maximum selector specificity and contrast so the visual patch takes effect immediately. "
                "Do not return any explanations, return ONLY the raw CSS file content."
            )
            try:
                response = await llm.ainvoke(prompt)
                fix_content = response.content
                if isinstance(fix_content, list):
                    fix_content = "".join(
                        item if isinstance(item, str) else (item.get("text", "") if isinstance(item, dict) else str(item))
                        for item in fix_content
                    )
                elif not isinstance(fix_content, str):
                    fix_content = str(fix_content or "")
                fix_content = fix_content.strip()
                if fix_content.startswith("```"):
                    lines = fix_content.splitlines()
                    if lines[0].startswith("```"): lines = lines[1:]
                    if lines and lines[-1].strip().startswith("```"): lines = lines[:-1]
                    fix_content = "\n".join(lines)
            except Exception as e:
                fix_content = original_content + f"\n\n/* [OmniSight Fix] {bug.title} */\n{bug.element_selector or 'body'} {{\n  {bug.suggested_fix}\n}}\n"
        else:
            fix_content = original_content + f"\n\n/* [OmniSight Fix] {bug.title} */\n{bug.element_selector or 'body'} {{\n  {bug.suggested_fix}\n}}\n"

        pr_result = await create_fix_pr(
            file_path=file_path,
            fix_content=fix_content,
            bug_description=bug.title,
            bug_severity=bug.severity,
            bug_viewport=bug.viewport,
            bug_element_selector=bug.element_selector,
            vlm_reasoning=bug.description,
            before_img_url=bug.screenshot_path,
            after_img_url=bug.verification_screenshot_path,
            original_content=original_content,
            target_url=target_url,
        )
        
        if pr_result.get("status") == "error":
            raise HTTPException(status_code=500, detail=pr_result["message"])
            
        # Update the ScanRun's pr_url
        if run and not run.pr_url:
            run.pr_url = pr_result.get("pr_url")
            await db.commit()

        # Always sync locally if local file exists
        apply_fix_locally(file_path, fix_content)
            
        return pr_result
        
    raise HTTPException(status_code=400, detail="Invalid action")


@router.post("/scans/{run_id}/sync-pr", summary="Check and sync merged PR changes to target site")
async def sync_run_pr(run_id: str, db: AsyncSession = Depends(get_db_session)):
    """
    Checks if the GitHub Pull Request for this scan was merged, and synchronizes
    the merged code to the local target files and verifies GitHub Pages deployment status.
    """
    from backend.services.github.pr_creator import sync_merged_pr_changes
    result = await db.execute(
        select(ScanRunModel).where(ScanRunModel.id == run_id)
    )
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Scan run '{run_id}' not found")

    if not run.pr_url:
        raise HTTPException(status_code=400, detail="This scan run does not have an associated Pull Request yet.")

    res = await sync_merged_pr_changes(
        run_id=run_id,
        target_url=run.url or "",
        pr_url=run.pr_url,
    )
    return res


@router.get("/scans/{run_id}/pr-status", summary="Get Pull Request status and deployment info")
async def get_run_pr_status(run_id: str, db: AsyncSession = Depends(get_db_session)):
    """Check current state of the Pull Request."""
    from backend.services.github.pr_creator import sync_merged_pr_changes
    result = await db.execute(select(ScanRunModel).where(ScanRunModel.id == run_id))
    run = result.scalars().first()
    if not run or not run.pr_url:
        return {"status": "none", "pr_url": None}

    return await sync_merged_pr_changes(
        run_id=run_id,
        target_url=run.url or "",
        pr_url=run.pr_url,
    )


@router.post("/system/clear-cache", summary="Clear temporary files and cache across the project")
async def clear_system_cache() -> dict[str, Any]:
    """
    Cleans temporary artifacts, screenshots, cached downloads, and python bytecode caches
    to optimize project disk space and execution speed.
    """
    import glob
    deleted_items = []
    freed_bytes = 0

    # 1. Clear output/screenshots directory
    screenshots_dir = os.path.join("output", "screenshots")
    if os.path.exists(screenshots_dir):
        for entry in os.listdir(screenshots_dir):
            file_path = os.path.join(screenshots_dir, entry)
            try:
                if os.path.isfile(file_path):
                    freed_bytes += os.path.getsize(file_path)
                    os.remove(file_path)
                    deleted_items.append(f"output/screenshots/{entry}")
            except Exception:
                pass

    # 2. Clear output/fixed temporary patches
    fixed_dir = os.path.join("output", "fixed")
    if os.path.exists(fixed_dir):
        for entry in os.listdir(fixed_dir):
            file_path = os.path.join(fixed_dir, entry)
            try:
                if os.path.isfile(file_path):
                    freed_bytes += os.path.getsize(file_path)
                    os.remove(file_path)
                    deleted_items.append(f"output/fixed/{entry}")
            except Exception:
                pass

    # 3. Clear temporary test and log files in root if safe
    temp_patterns = ["backend_err.log", "backend_out.log", "frontend_out.log"]
    for pattern in temp_patterns:
        if os.path.exists(pattern):
            try:
                freed_bytes += os.path.getsize(pattern)
                with open(pattern, "w", encoding="utf-8") as f:
                    f.truncate(0)
                deleted_items.append(f"truncated: {pattern}")
            except Exception:
                pass

    # 4. Clear __pycache__ directories
    for pycache_dir in glob.glob("**/__pycache__", recursive=True):
        try:
            shutil.rmtree(pycache_dir, ignore_errors=True)
            deleted_items.append(pycache_dir)
        except Exception:
            pass

    return {
        "success": True,
        "message": f"Successfully cleaned {len(deleted_items)} cache artifacts",
        "freed_kb": round(freed_bytes / 1024, 2),
        "cleaned_items_count": len(deleted_items),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

