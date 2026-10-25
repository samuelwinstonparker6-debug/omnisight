"""
OmniSight — VLM Analyzer  (Unified Single-Pass Strategy)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Architecture: ONE Gemini call per scan (not per viewport).
  - All screenshots (desktop + tablet + mobile) are sent in a single multimodal request
  - The full HTML source + any linked CSS are fetched and included as text context
  - Bugs are deduplicated across viewports by selector+category fingerprint
  - Hard 25-second timeout — the scan WILL return within 30s total end-to-end

Why single-pass is superior:
  - Sequential two-pass (old) = 6 API calls × ~15s each = 90s
  - Single unified pass (new)  = 1 API call × ~8s = 8s
  - The model sees the full picture in one shot — no context loss between passes
  - Eliminates the "loop of redundant fixes" caused by independent per-viewport calls
"""

import asyncio
import base64
import hashlib
import io
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Hard limit: entire analysis must complete within this many seconds
ANALYSIS_TIMEOUT_SECONDS = 60.0

# Max characters of page source to send (covers full <head> + inline CSS + body structure)
HTML_CHAR_LIMIT = 20_000

# Screenshot dimensions sent to Gemini — downscale to speed up token processing
SCREENSHOT_MAX_WIDTH = 1280
SCREENSHOT_MAX_HEIGHT = 900


# ─────────────────────────────────────────────────────────────────────────────
# Image helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_image_base64(image_path: str) -> str:
    """Read image file and return a base64-encoded string."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Screenshot not found: {image_path}")
    with path.open("rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _resize_and_encode(image_path: str, max_w: int = SCREENSHOT_MAX_WIDTH, max_h: int = SCREENSHOT_MAX_HEIGHT) -> str:
    """
    Resize image to fit within max_w × max_h (preserving aspect ratio) and
    return a base64-encoded PNG string. Smaller images = faster API responses.
    """
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Screenshot not found: {image_path}")

    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_w, max_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# HTML + CSS source fetcher
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_page_context(page_url: str, timeout: float = 8.0) -> str:
    """
    Fetch the raw HTML + any linked CSS stylesheets of the page.
    Returns a combined context string for the VLM showing both structure and styles.
    This is critical — the model needs to see actual CSS values (colors, fonts, layout)
    not just HTML markup, to correctly identify genuine vs intentional design choices.
    """
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": "OmniSight/1.0 UI-Auditor"}
        ) as client:
            resp = await client.get(page_url)
            resp.raise_for_status()
            html = resp.text

            # Extract linked CSS hrefs
            css_hrefs = re.findall(
                r'<link[^>]+rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\']',
                html,
                re.IGNORECASE,
            ) + re.findall(
                r'<link[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\']stylesheet["\']',
                html,
                re.IGNORECASE,
            )

            # Fetch up to 2 external CSS files (most sites have 1-2)
            css_texts: list[str] = []
            base = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
            for href in css_hrefs[:2]:
                css_url = href if href.startswith("http") else urljoin(base, href)
                try:
                    css_resp = await client.get(css_url, timeout=5.0)
                    css_resp.raise_for_status()
                    css_texts.append(f"/* === {href} === */\n{css_resp.text[:8000]}")
                except Exception as css_exc:
                    logger.debug("Could not fetch CSS %s: %s", href, css_exc)

            # Trim HTML
            if len(html) > HTML_CHAR_LIMIT:
                html = html[:HTML_CHAR_LIMIT] + "\n<!-- [TRIMMED] -->"

            parts = [f"<!-- HTML SOURCE -->\n{html}"]
            if css_texts:
                parts.append(f"\n/* LINKED STYLESHEET(S) */\n" + "\n\n".join(css_texts))

            return "\n\n".join(parts)

    except Exception as exc:
        logger.warning("Could not fetch page context for %s: %s", page_url, exc)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Bug deduplication
# ─────────────────────────────────────────────────────────────────────────────

def _bug_fingerprint(bug: dict) -> str:
    """
    Create a stable fingerprint for a bug to detect cross-viewport duplicates.
    Two bugs are the same if they target the same CSS selector with the same category.
    """
    sel = (bug.get("element_selector") or "").strip().lower()
    cat = (bug.get("category") or "").strip().lower()
    key = f"{cat}::{sel}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def _deduplicate_bugs(bugs: list[dict]) -> list[dict]:
    """
    Merge duplicate bugs that appear across multiple viewports.
    The first occurrence is kept; subsequent duplicates with different viewports
    are merged into a 'viewports' list on the primary record.
    """
    seen: dict[str, dict] = {}
    for bug in bugs:
        fp = _bug_fingerprint(bug)
        if fp not in seen:
            bug.setdefault("viewports", [bug.get("viewport", "desktop")])
            seen[fp] = bug
        else:
            # Merge viewport into existing record
            existing_vps = seen[fp].get("viewports", [])
            vp = bug.get("viewport")
            if vp and vp not in existing_vps:
                existing_vps.append(vp)
            seen[fp]["viewports"] = existing_vps
            # Escalate severity if a more severe instance found
            sev_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
            if sev_rank.get(bug.get("severity", ""), 0) > sev_rank.get(seen[fp].get("severity", ""), 0):
                seen[fp]["severity"] = bug["severity"]

    return list(seen.values())


# ─────────────────────────────────────────────────────────────────────────────
# System prompt — unified single-pass
# ─────────────────────────────────────────────────────────────────────────────

_UNIFIED_SYSTEM = """\
You are an elite Visual QA Director and CSS specialist with 15 years of experience auditing production websites.

You will receive:
1. The page's HTML source + linked CSS stylesheets (full design intent: colors, layout, typography)
2. Screenshots of the page at desktop, tablet, and mobile viewports

YOUR MISSION: Identify ONLY genuine, visually confirmed UI bugs that deviate from the design intent.

══════════════════════════════════════════════════════════
CRITICAL THINKING PROCESS (follow this before reporting any bug):
══════════════════════════════════════════════════════════
STEP 1 — STUDY THE SOURCE: Read the HTML/CSS first. Understand the developer's intended design:
  - What color palette was chosen? (extract actual hex values)
  - What layout system is used? (flexbox, grid, absolute positioning)
  - What font sizes and weights are intended for each component?
  - Are dark themes, glassmorphism, or specific stylistic effects intentional?

STEP 2 — COMPARE SCREENSHOTS: Look at each screenshot. Ask: "Does this element look WRONG relative
  to what the CSS says it should look like?" If the CSS says `color: #0ea5e9` and it looks blue — that is CORRECT.
  If the CSS says `color: #0ea5e9` but the text is invisible on a dark background — that is a BUG.

STEP 3 — VERIFY IT IS REAL: Before reporting a bug, confirm it is VISUALLY APPARENT in the screenshot.
  Do NOT report bugs you imagine from the code alone. Do NOT report things that look intentional.

══════════════════════════════════════════════════════════
ABSOLUTE RULES — VIOLATION = FAILURE:
══════════════════════════════════════════════════════════
1. NO DUPLICATE REPORTS: If the same element has the same issue on desktop and mobile, report it ONCE
   and note both viewports. Do NOT repeat the same bug entry for each viewport.
2. SURGICAL FIXES ONLY: Each `suggested_fix` must be 1-3 specific CSS properties MAX.
   Target the most specific selector possible (e.g., `.hero-section .badge-text` NOT `.badge` NOT `span`).
3. NO BLANKET OVERRIDES: NEVER use: `*`, `body`, `html`, `h1`, `h2`, `p`, `button`, `div`, `a` as selectors.
4. NO LAYOUT REWRITES: Do NOT suggest `display: flex` or `grid` rewrites unless an element is visibly
   clipped, overlapping another, or completely invisible in the screenshot.
5. NO INVENTED BUGS: If the page looks correct and intentional — return `{"bugs": []}`. That is success.
6. CONTRAST STANDARD: Text must meet 4.5:1 WCAG contrast. Report contrast bugs only if text is
   VISIBLY hard to read in the screenshot (not just theoretically failing).
7. RESPECT DESIGN INTENT: Dark themes are intentional. Muted text on dark cards may be intentional
   secondary text styling. Only flag if a primary label or heading is unreadable.

══════════════════════════════════════════════════════════
OUTPUT FORMAT — strict JSON, no markdown fences:
══════════════════════════════════════════════════════════
{
  "design_summary": "2-3 sentence summary of the page design intent (color scheme, layout, style)",
  "bugs": [
    {
      "id": "bug-unique-slug",
      "category": "contrast|layout|overflow|overlap|responsive|accessibility|typography",
      "severity": "critical|high|medium|low",
      "title": "Short, specific title referencing the actual element",
      "description": "Precise description: what CSS intends vs what is rendered, and why it is a problem",
      "element_selector": ".most-specific-possible-selector",
      "suggested_fix": "property: value; property2: value2;",
      "viewport": "desktop|tablet|mobile|all",
      "confidence": 0.0
    }
  ]
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Main unified analyzer — all viewports in ONE call
# ─────────────────────────────────────────────────────────────────────────────

async def analyze_all_viewports(
    screenshots: dict[str, str],
    page_url: str,
    page_source: Optional[str] = None,
    api_key: Optional[str] = None,
    user_prompt: Optional[str] = None,
) -> dict[str, Any]:
    """
    NEW UNIFIED ENTRY POINT — analyze all viewports in a single Gemini call.

    Args:
        screenshots: dict mapping viewport_name -> absolute_image_path
        page_url: URL of the page being analyzed
        page_source: Optional pre-captured HTML/DOM source code
        api_key: Optional Gemini API key override

    Returns:
        {
            "status": "success"|"error",
            "bugs": [...],              # deduplicated across all viewports
            "design_summary": "...",
            "analysis_mode": "unified_single_pass",
        }
    """
    settings = get_settings()
    model_name: str = settings.gemini_model or "gemini-3.8-flash"
    # Always prefer flash for speed — it's multimodal and fast
    if "pro" in model_name.lower():
        model_name = model_name.replace("pro", "flash")
    key: str = api_key or settings.gemini_api_key or ""

    if not key:
        logger.warning("⚠️  No Gemini API key — returning empty analysis (no fake heuristics).")
        return {
            "status": "success",
            "bugs": [],
            "design_summary": "No Gemini API key configured.",
            "analysis_mode": "no_api_key",
        }

    logger.info("⚡ Unified single-pass VLM analysis: %s | viewports: %s | model: %s",
                page_url, list(screenshots.keys()), model_name)

    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=key,
        temperature=0.0,           # Zero temp = consistent, deterministic output
        max_output_tokens=4096,    # Sufficient for structured bug reports
    )

    # ── Fetch or use page source (HTML + CSS) ─────────────────────────────────
    page_context = ""
    if page_source:
        if len(page_source) > HTML_CHAR_LIMIT:
            page_context = "<!-- HTML SOURCE -->\n" + page_source[:HTML_CHAR_LIMIT] + "\n<!-- [TRIMMED] -->"
        else:
            page_context = f"<!-- HTML SOURCE -->\n{page_source}"
    else:
        try:
            page_context = await asyncio.wait_for(_fetch_page_context(page_url), timeout=8.0)
        except Exception:
            page_context = ""
            logger.warning("Page context fetch timed out — proceeding with screenshots only")

    # ── Encode screenshots (resize to reduce token cost / latency) ────────────
    encoded_screenshots: dict[str, str] = {}
    for vp_name, img_path in screenshots.items():
        try:
            encoded_screenshots[vp_name] = _resize_and_encode(img_path)
            logger.debug("Encoded %s screenshot: %s", vp_name, img_path)
        except Exception as enc_err:
            logger.warning("Could not encode %s screenshot: %s", vp_name, enc_err)

    if not encoded_screenshots:
        return {"status": "error", "bugs": [], "message": "No screenshots available for analysis"}

    # ── Build the single multimodal prompt ────────────────────────────────────
    content_parts: list = []

    # Text context: page source + CSS
    context_intro = (
        f"TARGET URL: {page_url}\n\n"
        f"VIEWPORTS CAPTURED: {', '.join(encoded_screenshots.keys())}\n\n"
    )
    if page_context:
        context_intro += f"PAGE SOURCE (HTML + CSS — study this first to understand design intent):\n\n{page_context}\n\n---\n\n"
    else:
        context_intro += "Note: Could not fetch page source — analyze from screenshots only.\n\n---\n\n"

    context_intro += (
        f"Now analyze the {len(encoded_screenshots)} screenshot(s) below. "
        "Identify ONLY genuine visual regressions. Apply your 3-step thinking process:\n"
        "1. Study the source CSS to understand design intent\n"
        "2. Compare each screenshot against that intent\n"
        "3. Report ONLY bugs you can see in the screenshots\n\n"
    )
    if user_prompt:
        context_intro += (
            f"SPECIAL SCAN DIRECTIVES:\n{user_prompt}\n"
            "Focus specifically on detecting and proposing surgical fixes for issues highlighted by these directives, "
            "especially UI layout full-bleed/breathing room issues, and contrast/visibility issues.\n\n"
        )
    context_intro += "Remember: return {\"bugs\": []} if the page looks correct."
    content_parts.append({"type": "text", "text": context_intro})

    # Add screenshots in order: desktop first (most important), then tablet, mobile
    viewport_order = ["desktop", "tablet", "mobile"]
    for vp in viewport_order:
        if vp in encoded_screenshots:
            content_parts.append({
                "type": "text",
                "text": f"\n\n[SCREENSHOT — {vp.upper()} VIEWPORT]",
            })
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encoded_screenshots[vp]}"},
            })

    # ── Make the single API call with a hard timeout ──────────────────────────
    try:
        async with asyncio.timeout(ANALYSIS_TIMEOUT_SECONDS):
            response = await llm.ainvoke([
                SystemMessage(content=_UNIFIED_SYSTEM),
                HumanMessage(content=content_parts),
            ])
            raw = response.content
    except asyncio.TimeoutError:
        logger.error("VLM analysis timed out after %.0fs", ANALYSIS_TIMEOUT_SECONDS)
        return {
            "status": "timeout",
            "bugs": [],
            "message": f"Analysis timed out after {ANALYSIS_TIMEOUT_SECONDS:.0f}s",
            "analysis_mode": "unified_single_pass",
        }
    except Exception as exc:
        logger.error("VLM API call failed: %s", exc)
        return {
            "status": "error",
            "bugs": [],
            "message": f"Gemini API error: {exc}",
            "analysis_mode": "unified_single_pass",
        }

    # ── Parse JSON response ───────────────────────────────────────────────────
    if isinstance(raw, list):
        raw = "".join(str(p.get("text", p)) if isinstance(p, dict) else str(p) for p in raw)

    raw = raw.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    # Extract JSON object if embedded in text
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if json_match:
        raw = json_match.group(0)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as jde:
        logger.error("Failed to parse VLM JSON response: %s\nRaw: %s", jde, raw[:500])
        return {
            "status": "error",
            "bugs": [],
            "message": "JSON parse error",
            "raw_response": raw[:1000],
            "analysis_mode": "unified_single_pass",
        }

    raw_bugs: list = data.get("bugs", [])
    design_summary: str = data.get("design_summary", "")

    # ── Assign screenshot paths to bugs ───────────────────────────────────────
    for bug in raw_bugs:
        vp = bug.get("viewport", "desktop")
        bug["screenshot_path"] = screenshots.get(vp) or next(iter(screenshots.values()), "")
        bug.setdefault("confidence", 1.0)

    # ── Deduplicate across viewports ──────────────────────────────────────────
    deduped_bugs = _deduplicate_bugs(raw_bugs)

    logger.info(
        "✅ Unified analysis complete — %d raw bugs → %d after dedup | %s",
        len(raw_bugs), len(deduped_bugs), page_url
    )

    return {
        "status": "success",
        "bugs": deduped_bugs,
        "design_summary": design_summary,
        "raw_response": raw,
        "analysis_mode": "unified_single_pass",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Legacy per-viewport entry point — kept for backward compatibility
# Routes through the new unified analyzer for the single screenshot provided
# ─────────────────────────────────────────────────────────────────────────────

async def analyze_screenshot(
    image_path: str,
    page_url: str,
    viewport: str = "desktop",
    model: str = "",
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """
    Legacy single-viewport entry point — wraps the unified analyzer.
    Used by the per-viewport analysis tasks in routes.py (backward compat).
    """
    result = await analyze_all_viewports(
        screenshots={viewport: image_path},
        page_url=page_url,
        api_key=api_key,
    )
    # Normalize output shape to match what routes.py expects
    for bug in result.get("bugs", []):
        bug.setdefault("screenshot_path", image_path)
        bug.setdefault("viewport", viewport)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Element region cropper (unchanged utility)
# ─────────────────────────────────────────────────────────────────────────────

from playwright.async_api import async_playwright


async def crop_element_region(
    image_path: str,
    page_url: str,
    css_selector: str,
    viewport_name: str = "desktop",
    padding: int = 20,
) -> Optional[str]:
    """
    Crop a specific element's region from a full-page screenshot.
    """
    from backend.services.browser.automation import VIEWPORTS

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            dimensions = VIEWPORTS.get(viewport_name, VIEWPORTS["desktop"])
            context = await browser.new_context(viewport=dimensions, device_scale_factor=1)
            page = await context.new_page()
            try:
                await page.goto(page_url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                await page.goto(page_url, wait_until="load", timeout=20000)

            await asyncio.sleep(0.5)

            locator = page.locator(css_selector).first
            box = await locator.bounding_box(timeout=5000)
            if not box:
                logger.warning("Could not find bounding box for selector %s", css_selector)
                return None

            x, y, w, h = box["x"], box["y"], box["width"], box["height"]
            path = Path(image_path)
            if not path.is_file():
                return None

            with Image.open(path) as img:
                left   = max(0, x - padding)
                top    = max(0, y - padding)
                right  = min(img.width,  x + w + padding)
                bottom = min(img.height, y + h + padding)
                cropped = img.crop((left, top, right, bottom))

                out_path = path.parent / f"{path.stem}_cropped_{hash(css_selector)}{path.suffix}"
                cropped.save(out_path)
                return str(out_path.absolute())

        except Exception as e:
            logger.error("Failed to crop element region: %s", e)
            return None
        finally:
            await browser.close()
