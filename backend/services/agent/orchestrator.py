"""
OmniSight — Agent Orchestrator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

LangChain-based orchestrator that runs the full self-healing pipeline:
1. Trigger browser to capture screenshots
2. Send to VLM for bug analysis
3. Generate CSS/HTML fixes
4. Create GitHub PR with fix

Uses a ReAct-style agent with tool-calling for each step.
"""

import logging
from typing import Any

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate
import os
import subprocess

from backend.core.config import get_settings

logger = logging.getLogger(__name__)


@tool
async def capture_ui(url: str) -> dict:
    """Captures screenshots of the given UI URL across different viewports."""
    from backend.services.browser.automation import capture_screenshots
    return await capture_screenshots(url=url, headless=True)


@tool
async def analyze_ui(image_path: str, url: str, viewport: str) -> dict:
    """Analyzes a UI screenshot for bugs."""
    from backend.services.vlm.analyzer import analyze_screenshot
    return await analyze_screenshot(image_path=image_path, page_url=url, viewport=viewport)


@tool
async def apply_fix(file_path: str, fix_content: str) -> str:
    """Applies a fix to a local file."""
    import os
    full_path = os.path.join(os.getcwd(), file_path)
    try:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(fix_content)
        return f"Successfully applied fix to {file_path}. You should now take a new screenshot to verify it."
    except Exception as e:
        return f"Error applying fix: {e}"


@tool
async def create_github_pr(file_path: str, bug_description: str, fix_content: str) -> str:
    """Creates a pull request on GitHub for the fix."""
    from backend.services.github.pr_creator import create_fix_pr
    result = await create_fix_pr(file_path, fix_content, bug_description)
    return str(result)


@tool
async def sync_and_restart(repo_path: str = ".") -> str:
    """Pull latest changes from git and restart backend and frontend servers.
    Returns a summary string of actions performed.
    """
    try:
        cwd = os.path.abspath(repo_path)
        # Pull latest changes
        pull_cmd = "git pull"
        pull_result = subprocess.run(pull_cmd, cwd=cwd, shell=True, capture_output=True, text=True)
        output = f"Git pull output:\n{pull_result.stdout}\n"
        # Restart backend (uvicorn) and frontend (npm run dev) if running
        # Attempt to kill existing processes (simple approach)
        # Note: On Windows, use taskkill; on *nix, use pkill.
        if os.name == "nt":
            # Kill processes by name (python for uvicorn, node for frontend)
            subprocess.run("taskkill /IM python.exe /F", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run("taskkill /IM node.exe /F", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run("pkill -f uvicorn", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run("pkill -f npm", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        output += "Terminated existing backend/frontend processes.\n"
        # Start backend server
        backend_cmd = "python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000"
        subprocess.Popen(backend_cmd, cwd=cwd, shell=True)
        # Start frontend dev server
        frontend_dir = os.path.join(cwd, "frontend")
        subprocess.Popen("npm run dev", cwd=frontend_dir, shell=True)
        output += "Started new backend and frontend servers."
        return output
    except Exception as e:
        return f"Error during sync and restart: {e}"


async def run_pipeline(
    target_url: str,
    auto_fix: bool = False,
    create_pr: bool = False,
) -> dict[str, Any]:
    """
    Execute the full OmniSight self-healing pipeline using a LangChain agent.

    Args:
        target_url: URL of the application to scan and heal.
        auto_fix: If True, automatically generate fix suggestions.
        create_pr: If True, create a GitHub PR with the fixes.

    Returns:
        Pipeline execution result with scan findings and actions taken.
    """
    logger.info("🤖 Pipeline execution requested for: %s", target_url)
    
    settings = get_settings()
    
    if not settings.gemini_api_key:
        logger.warning("Gemini API key is missing. Attempting to proceed with fallback mock responses.")

        
    llm = ChatGoogleGenerativeAI(
        model=settings.gemini_model or "gemini-3.5-flash-lite",
        google_api_key=settings.gemini_api_key,
        temperature=0.0,
        max_output_tokens=8192,
    )
    
    tools = [capture_ui, analyze_ui, apply_fix, create_github_pr]
    
    agent_executor = create_react_agent(
        llm, 
        tools
    )
    
    command = f"Scan {target_url} for UI bugs. Capture screenshots first, then analyze them."
    if auto_fix:
        command += " If you find any bugs, formulate a CSS/HTML fix and apply it."
    if create_pr:
        command += " After applying the fix, create a GitHub PR for it."
        
    if not settings.gemini_api_key:
        logger.warning("Mocking agent execution for pipeline — no API key.")
        from backend.services.browser.automation import capture_screenshots
        from backend.services.vlm.analyzer import analyze_screenshot

        # Capture screenshots to get a valid image
        res = await capture_screenshots(target_url, headless=True)
        if res.get("status") == "success" and res.get("screenshots"):
            image_path = list(res["screenshots"].values())[0]
            await analyze_screenshot(image_path, target_url, "desktop")

        return {
            "status": "completed",
            "target_url": target_url,
            "agent_output": "Mock agent completed (no API key). Captured UI and ran heuristic analysis."
        }
        
    try:
        system_msg = (
            "You are OmniSight, an autonomous AI UI/UX QA agent powered by Gemini. "
            "Your goal is to audit a live URL for visual regressions and produce surgical, high-contrast CSS fixes.\n\n"
            "CORE QUALITY STANDARDS:\n"
            "- PREVENT WASHED-OUT / BLURRED HEADINGS: All section titles, headpoints, badges, and labels must be crisp, legible, and sharply contrasted against backgrounds (WCAG 4.5:1+). Never blend headings into background shades or introduce opacity/blur that degrades legibility.\n"
            "- SURGICAL FIXES ONLY: Every fix MUST use the exact specific selector (e.g. `.hero .header-title`, `.section-head h2`) with a maximum of 2-3 CSS properties. Use high-contrast color tokens like `#f8fafc` or `color: #ffffff; text-shadow: none;`. NEVER use blanket destructive tag overrides (e.g. `h1, h2, p` or `*`).\n\n"
            "PIPELINE RULES (Follow in exact order):\n"
            "1. CAPTURE: Take screenshots across viewports (desktop, tablet, mobile) using capture_ui.\n"
            "2. ANALYZE: Call analyze_ui for each viewport — the analyzer inspects design intent and flags regressions.\n"
            "3. TRIAGE: Group bugs by severity. Prioritize critical and high contrast/visibility bugs. Ignore items with confidence < 0.7.\n"
            "4. FIX (only if auto_fix=True): Apply surgical, non-destructive CSS patches addressing low contrast, blurred text, or clipped layouts.\n"
            "5. VERIFY VISUALLY (MANDATORY BEFORE PR): After applying a fix, you MUST capture a new screenshot using capture_ui and re-run analyze_ui. Confirm visually that the text/heading is now crisp, readable, and that no new layout regressions were introduced.\n"
            "6. PR CREATION: Call create_github_pr ONLY AFTER the verification pass confirms the fix is successful and visual quality is preserved. If a fix fails verification after 2 attempts, escalate and abort PR creation rather than applying destructive overrides.\n"
        )
        result = await agent_executor.ainvoke({"messages": [("system", system_msg), ("user", command)]})
        # If PR creation was requested and successful, sync repo and restart services
        if create_pr:
            sync_msg = await sync_and_restart(repo_path=".")
            logger.info("Sync and restart output: %s", sync_msg)
        return {
            "status": "completed",
            "target_url": target_url,
            "agent_output": result["messages"][-1].content
        }
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        return {
            "status": "error",
            "target_url": target_url,
            "message": str(e)
        }
