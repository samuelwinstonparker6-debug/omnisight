"""
OmniSight — AI Design Studio Routes (v2)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Endpoints:
  POST /api/v1/design/interpret   → Classify intent + produce action plan from prompt
  POST /api/v1/design/generate    → Full pipeline: interpret → generate CSS → optionally detect bugs → push PR
  POST /api/v1/design/prompt      → (legacy) Generate CSS only (no PR)
  POST /api/v1/design/push        → (legacy) Push pre-generated CSS to GitHub PR

Design Studio is a superset of OmniSight bug-detection:
  - "design" mode: generates CSS/HTML changes from a natural-language prompt and creates a PR
  - "bugfix" mode: runs the OmniSight VLM pipeline then applies + PRs the fixes
  - "both" mode: detects bugs AND applies prompt-driven changes in a single PR
"""

import logging
import uuid
import asyncio
import re
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.config import get_settings
from backend.services.agent.design_interpreter import interpret_prompt, classify_intent

logger = logging.getLogger(__name__)
design_router = APIRouter(prefix="/api/v1/design", tags=["design-studio"])


# ─────────────────────────────────────────────────────────────
# Request / Response schemas
# ─────────────────────────────────────────────────────────────

class DesignPromptRequest(BaseModel):
    prompt: str
    target_url: str = ""
    existing_css: str = ""


class DesignGenerateRequest(BaseModel):
    """Full-pipeline request: interpret + generate + optional PR."""
    prompt: str
    target_url: str = ""
    create_pr: bool = False           # If True, push changes to GitHub PR
    run_bug_detection: bool = False   # If True (or prompt implies bugfix), run VLM scan first
    existing_css: str = ""


class DesignPushRequest(BaseModel):
    css: str
    prompt: str = ""
    target_url: str = ""
    branch_suffix: str = ""


class InterpretRequest(BaseModel):
    prompt: str
    target_url: str = ""
    page_source: str = ""


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

CSS_GENERATION_SYSTEM = (
    "You are an elite, surgical UI/UX designer and principal CSS architect.\n"
    "The user will give you instructions describing visual styling improvements for their web page.\n\n"
    "CRITICAL RULES (Violating these will break the website):\n"
    "1. OUTPUT FORMAT: Output ONLY raw valid CSS with NO markdown fences (no ```css), NO comments explaining your life, and NO <style> tags.\n"
    "2. SURGICAL SELECTORS ONLY:\n"
    "   - NEVER use blanket, destructive tag selectors like `h1, h2, h3, h4, h5, h6`, `*`, `p`, `span`, `div`, or loose wildcards like `[id*='heading']`.\n"
    "   - ALWAYS target specific classes, IDs, or contextual selectors (e.g. `.section-title`, `.hero-title`, `.project-card h3`, `.stack-title`, `#projects h2`).\n"
    "3. PRESERVE ARTWORK & GRADIENTS (DO NOT WIPE THEM OUT):\n"
    "   - NEVER output `background: none !important`, `-webkit-background-clip: initial !important`, or `-webkit-text-fill-color: initial !important` unless explicitly commanded to delete gradients.\n"
    "   - To brighten text on dark backgrounds, increase contrast surgically.\n"
    "4. MINIMAL OVERRIDES:\n"
    "   - Provide ONLY 2-4 clean properties per targeted selector.\n"
    "   - Ensure all text exceeds WCAG AA contrast (>= 4.5:1) while preserving the designer's original brand identity and theme."
)


def _strip_fences(text: Any) -> str:
    if isinstance(text, list):
        text = "".join(
            item if isinstance(item, str) else (item.get("text", "") if isinstance(item, dict) else str(item))
            for item in text
        )
    elif not isinstance(text, str):
        text = str(text or "")
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


async def _generate_css_from_prompt(prompt: str, target_url: str = "", existing_css: str = "") -> str:
    """Call Gemini to produce CSS from the design prompt."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="Gemini API key is not configured.")

    parts = ["Design request: " + prompt.strip()]
    if target_url:
        parts.append("Website URL for context: " + target_url)
    if existing_css:
        parts.append("Current stylesheet:\n```css\n" + existing_css + "\n```")
    user_message = "\n\n".join(parts)

    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import SystemMessage, HumanMessage

    model_name = settings.gemini_model or "gemini-1.5-flash"
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=settings.gemini_api_key,
        temperature=0.6,
        max_output_tokens=4096,
    )
    messages = [SystemMessage(content=CSS_GENERATION_SYSTEM), HumanMessage(content=user_message)]
    response = await llm.ainvoke(messages)
    css = _strip_fences(response.content or "")
    if not css:
        raise HTTPException(status_code=502, detail="Model returned an empty response.")
    return css


def _push_to_github_sync(
    css: str,
    prompt: str,
    target_url: str,
    suffix: str,
    token: str,
    repo_name: str,
    pr_title_prefix: str = "design",
) -> tuple[str, int, str, str]:
    """Create branch → commit CSS → open PR. Returns (pr_url, pr_number, branch_name, file_used)."""
    from github import Github, GithubException
    from backend.services.github.pr_creator import detect_target_stylesheet

    branch_name = f"omnisight/design-studio-{suffix}"
    g = Github(token)
    repo = g.get_repo(repo_name)
    default_branch = repo.default_branch
    base_sha = repo.get_branch(default_branch).commit.sha

    # Create or reset branch
    try:
        repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=base_sha)
    except GithubException as e:
        if e.status == 422:
            ref = repo.get_git_ref(f"heads/{branch_name}")
            ref.edit(sha=base_sha, force=True)
        else:
            raise

    # Detect or pick the stylesheet
    chosen_file = detect_target_stylesheet(repo, target_url)
    existing_sha = None
    existing_content = ""
    try:
        fc = repo.get_contents(chosen_file, ref=branch_name)
        existing_sha = fc.sha
        existing_content = fc.decoded_content.decode("utf-8", errors="replace")
    except GithubException:
        pass

    header = f"/* === OmniSight Design Studio — {suffix} === */\n"
    final_content = existing_content + "\n\n" + header + css + "\n"
    commit_msg = f"design: AI Design Studio update ({suffix})"

    if existing_sha:
        repo.update_file(chosen_file, commit_msg, final_content, existing_sha, branch=branch_name)
    else:
        repo.create_file(chosen_file, commit_msg, final_content, branch=branch_name)

    # Also apply locally so local server reflects changes immediately
    from backend.services.github.pr_creator import apply_fix_locally
    apply_fix_locally(chosen_file, final_content)

    prompt_section = (f"\n\n> **Design Prompt:** _{prompt}_\n") if prompt else ""
    pr_body = (
        f"## 🎨 OmniSight Design Studio — AI-Generated Update{prompt_section}\n\n"
        "This Pull Request was generated via the **OmniSight AI Design Studio**.\n\n"
        f"### Files Changed\n- `{chosen_file}`\n\n"
        f"### Generated CSS\n```css\n{css[:3000]}{'...(truncated)' if len(css) > 3000 else ''}\n```\n\n"
        "*Powered by OmniSight × Gemini AI*"
    )
    pr_title = f"{pr_title_prefix}: AI Design Studio — {(prompt or 'CSS patch')[:60]}"
    pr = repo.create_pull(title=pr_title, body=pr_body, head=branch_name, base=default_branch)
    return pr.html_url, pr.number, branch_name, chosen_file


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@design_router.post("/interpret", summary="Classify intent + produce action plan from a design prompt")
async def design_interpret(req: InterpretRequest) -> dict[str, Any]:
    """
    Interprets a natural-language design prompt and returns a structured action plan.
    The plan specifies intent (design / bugfix / both) and a list of code changes.
    """
    plan = await interpret_prompt(
        prompt=req.prompt,
        target_url=req.target_url,
        page_source=req.page_source,
    )
    return {"status": "success", **plan}


@design_router.post("/generate", summary="Full Design Studio pipeline: interpret → CSS → (bug detect) → PR")
async def design_generate(req: DesignGenerateRequest) -> dict[str, Any]:
    """
    Full pipeline:
    1. Classify prompt intent (design / bugfix / both)
    2. If bugfix/both: run VLM screenshot analysis to surface existing UI bugs
    3. Generate CSS/code changes from the prompt via Gemini
    4. Optionally push everything to a GitHub PR
    """
    settings = get_settings()
    suffix = uuid.uuid4().hex[:8]
    result: dict[str, Any] = {
        "status": "success",
        "suffix": suffix,
        "intent": None,
        "action_plan": None,
        "css": None,
        "bugs_detected": [],
        "pr_url": None,
        "pr_number": None,
        "branch": None,
        "file": None,
    }

    # ── Step 1: Interpret prompt ──────────────────────────────
    plan = await interpret_prompt(
        prompt=req.prompt,
        target_url=req.target_url,
    )
    result["intent"] = plan["intent"]
    result["action_plan"] = plan
    logger.info("Design Studio — intent=%s prompt=%r", plan["intent"], req.prompt[:80])

    # ── Step 2: Bug detection (if requested or implied) ───────
    run_bugs = req.run_bug_detection or plan["intent"] in ("bugfix", "both")
    if run_bugs and req.target_url:
        try:
            from backend.services.browser.automation import capture_screenshots
            from backend.services.vlm.analyzer import analyze_screenshot

            screenshots_dict, html_content = await capture_screenshots(url=req.target_url, headless=True)
            if screenshots_dict:
                for viewport, img_path in screenshots_dict.items():
                    analysis = await analyze_screenshot(
                        image_path=img_path,
                        page_url=req.target_url,
                        viewport=viewport,
                    )
                    bugs = analysis.get("bugs", [])
                    result["bugs_detected"].extend(bugs)
                    logger.info("Design Studio bug scan — viewport=%s bugs=%d", viewport, len(bugs))
        except Exception as e:
            logger.warning("Design Studio bug scan failed (non-fatal): %s", e)
            result["bug_scan_error"] = str(e)

    # ── Step 3: Generate CSS ──────────────────────────────────
    # Use css_patch from action plan if available, otherwise call LLM again
    css = (plan.get("css_patch") or "").strip()
    if not css:
        try:
            css = await _generate_css_from_prompt(
                prompt=req.prompt,
                target_url=req.target_url,
                existing_css=req.existing_css,
            )
        except Exception as e:
            logger.error("CSS generation failed: %s", e)
            raise HTTPException(status_code=500, detail=f"CSS generation failed: {e}")

    # If there were detected bugs, append CSS fixes for them
    if result["bugs_detected"]:
        from backend.services.vlm.code_fixer import generate_fixed_code
        # Synthesize CSS bug fixes and extract the style tag content
        bug_fixed_html = await generate_fixed_code(
            source_code="<html><head></head><body></body></html>",
            bugs=result["bugs_detected"],
        )
        bug_css_match = re.search(
            r"<style[^>]*id=['\"]omnisight-ai-fixes['\"][^>]*>(.*?)</style>",
            bug_fixed_html, re.DOTALL
        )
        if bug_css_match:
            css = css + "\n\n/* === OmniSight Bug Fixes === */\n" + bug_css_match.group(1).strip()

    result["css"] = css

    # ── Step 4: Push to GitHub PR (if requested) ──────────────
    if req.create_pr:
        token = settings.github_token.strip()
        repo_name = (
            _resolve_repo(req.target_url) or settings.github_repo or ""
        ).strip()

        if not token or token == "ghp_your-github-token-here":
            raise HTTPException(
                status_code=400,
                detail="GitHub is not connected. Please click 'Connect GitHub' first.",
            )
        if not repo_name or repo_name == "your-username/your-repo-name":
            raise HTTPException(
                status_code=400,
                detail="Could not determine the target GitHub repository from the URL.",
            )

        try:
            pr_title_prefix = "fix+design" if plan["intent"] == "both" else ("fix" if plan["intent"] == "bugfix" else "design")
            pr_url, pr_number, branch, file_used = await asyncio.to_thread(
                _push_to_github_sync,
                css, req.prompt, req.target_url, suffix, token, repo_name, pr_title_prefix,
            )
            result["pr_url"] = pr_url
            result["pr_number"] = pr_number
            result["branch"] = branch
            result["file"] = file_used
            logger.info("Design Studio PR #%d created: %s", pr_number, pr_url)
        except Exception as e:
            logger.error("Design Studio PR creation failed: %s", e)
            raise HTTPException(status_code=400, detail=f"PR creation failed: {e}")

    return result


def _resolve_repo(url: str) -> Optional[str]:
    """Helper to resolve GitHub repo from URL without importing the full module."""
    if not url:
        return None
    gh_pages = re.search(r"https?://([^.]+)\.github\.io/([^/?#]+)", url, re.IGNORECASE)
    if gh_pages:
        return f"{gh_pages.group(1)}/{gh_pages.group(2)}"
    gh_direct = re.search(r"https?://github\.com/([^/?#]+)/([^/?#]+)", url, re.IGNORECASE)
    if gh_direct:
        return f"{gh_direct.group(1)}/{gh_direct.group(2)}"
    return None


# ─────────────────────────────────────────────────────────────
# Legacy endpoints (kept for backward compatibility)
# ─────────────────────────────────────────────────────────────

@design_router.post("/prompt", summary="(Legacy) Generate CSS from a design prompt")
async def design_prompt(req: DesignPromptRequest) -> dict[str, Any]:
    """Calls Gemini with the user's design prompt and returns generated CSS."""
    try:
        css = await _generate_css_from_prompt(
            prompt=req.prompt,
            target_url=req.target_url,
            existing_css=req.existing_css,
        )
        settings = get_settings()
        model_name = settings.gemini_model or "gemini-1.5-flash"
        logger.info("Design prompt processed. CSS length: %d chars", len(css))
        return {"status": "success", "css": css, "model": model_name, "prompt_echo": req.prompt}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Design prompt generation failed: %s", e)
        raise HTTPException(status_code=500, detail="Generation failed: " + str(e))


@design_router.post("/push", summary="(Legacy) Push generated CSS to GitHub as a PR")
async def design_push(req: DesignPushRequest) -> dict[str, Any]:
    """Commits the user-approved CSS to the connected GitHub repo and opens a PR."""
    from github import GithubException
    settings = get_settings()
    token = (settings.github_token or "").strip()
    repo_name = (_resolve_repo(req.target_url) or settings.github_repo or "").strip()

    if not token or token == "ghp_your-github-token-here":
        raise HTTPException(status_code=400, detail="GitHub is not connected. Please click Connect GitHub first.")
    if not repo_name or repo_name == "your-username/your-repo-name":
        raise HTTPException(status_code=400, detail="Could not determine the target GitHub repository.")

    suffix = req.branch_suffix or uuid.uuid4().hex[:8]
    try:
        pr_url, pr_number, used_branch, css_file = await asyncio.to_thread(
            _push_to_github_sync,
            req.css, req.prompt, req.target_url, suffix, token, repo_name,
        )
        logger.info("Design PR #%d created: %s", pr_number, pr_url)
        return {
            "status": "success",
            "pr_url": pr_url,
            "pr_number": pr_number,
            "branch": used_branch,
            "file": css_file,
            "repo": repo_name,
        }
    except GithubException as e:
        logger.error("GitHub error during design push: %s", e)
        raise HTTPException(status_code=400, detail="GitHub error: " + str(e))
    except Exception as e:
        logger.exception("Design push failed: %s", e)
        raise HTTPException(status_code=500, detail="Push failed: " + str(e))
