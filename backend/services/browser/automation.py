"""
OmniSight — Browser Automation Module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Handles Playwright browser lifecycle and screenshot capture
across configurable viewports (desktop, tablet, mobile).
"""

import logging
import asyncio
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Tuple

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# Standard viewport configurations for responsive testing
VIEWPORTS = {
    "desktop": {"width": 1280, "height": 720},
    "tablet": {"width": 768, "height": 1024},
    "mobile": {"width": 320, "height": 568},
}

def _get_safe_filename(url: str, viewport_name: str) -> str:
    """Generate a safe filename from a URL and viewport."""
    parsed = urlparse(url)
    domain = parsed.netloc.replace(":", "_") or "localhost"
    path = parsed.path.strip("/").replace("/", "_") or "index"
    return f"{domain}_{path}_{viewport_name}.png"

async def capture_screenshots(
    url: str,
    output_dir: str = "./output/screenshots",
    viewports: Optional[dict[str, dict[str, int]]] = None,
    headless: bool = True,
) -> Tuple[dict[str, str], str]:
    """
    Capture full-page screenshots at multiple viewport sizes.

    Args:
        url: Target URL to screenshot.
        output_dir: Directory to save screenshot files.
        viewports: Dict of viewport configs. Defaults to desktop/tablet/mobile.
        headless: Run browser in headless mode.

    Returns:
        Tuple containing:
        - Dict mapping viewport name to absolute screenshot file path.
        - String containing the scraped HTML content.
    """
    logger.info("📸 Screenshot capture requested for: %s", url)
    
    # Ensure output directory exists
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    target_viewports = viewports or VIEWPORTS
    results = {}
    html_content = ""

    async def capture_single_viewport(browser, viewport_name, dimensions):
        nonlocal html_content
        logger.info(f"  → Capturing {viewport_name} viewport...")
        context = await browser.new_context(
            viewport=dimensions,
            device_scale_factor=1,
        )
        page = await context.new_page()
        try:
            # Fast, resilient page load: domcontentloaded + brief load settle + font check
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                try:
                    await page.wait_for_load_state("load", timeout=4000)
                except Exception:
                    pass
                try:
                    await page.evaluate("() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 1500))])")
                except Exception:
                    pass
            except Exception as nav_err:
                logger.warning(f"Navigation warning for {viewport_name}: {nav_err}")

            await asyncio.sleep(0.5)

            filename = _get_safe_filename(url, viewport_name)
            filepath = out_dir / filename

            try:
                await page.screenshot(
                    path=str(filepath),
                    full_page=False,
                    timeout=12000,
                    type="png",
                    animations="disabled"
                )
            except Exception as ss_err:
                logger.warning(f"Screenshot with disabled animations failed for {viewport_name}: {ss_err}, retrying standard capture")
                try:
                    await page.screenshot(
                        path=str(filepath),
                        full_page=False,
                        timeout=8000,
                        type="png"
                    )
                except Exception as retry_err:
                    logger.error(f"Screenshot completely failed for {viewport_name}: {retry_err}")
                    return None

            if not html_content:
                try:
                    html_content = await page.content()
                except Exception:
                    html_content = ""

            logger.info(f"  ✓ Saved to {filepath}")
            return (viewport_name, str(filepath.absolute()))
        except Exception as e:
            logger.error(f"Failed to capture {viewport_name}: {e}")
            return None
        finally:
            await context.close()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox", "--disable-extensions"]
        )
        try:
            tasks = [
                capture_single_viewport(browser, vp_name, dims)
                for vp_name, dims in target_viewports.items()
            ]
            captured = await asyncio.gather(*tasks)
            for item in captured:
                if item:
                    results[item[0]] = item[1]
        finally:
            await browser.close()

    return results, html_content

async def capture_with_injected_css(
    url: str,
    css_content: str,
    viewport_name: str,
    output_path: str,
    headless: bool = True
) -> str:
    """
    Launch Playwright at the specified viewport, navigate to url, inject the candidate CSS dynamically into the DOM,
    wait 500ms for layout reflow, and capture the screenshot to output_path.
    """
    logger.info("📸 Verification screenshot capture requested for: %s with injected CSS", url)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            dimensions = VIEWPORTS.get(viewport_name, VIEWPORTS["desktop"])
            context = await browser.new_context(
                viewport=dimensions,
                device_scale_factor=1,
            )
            page = await context.new_page()
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            except Exception:
                await page.goto(url, wait_until="load", timeout=25000)
            
            # Inject CSS dynamically
            await page.add_style_tag(content=css_content)
            
            # Wait for layout reflow
            await asyncio.sleep(0.5)
            
            # Ensure directory exists
            out_path = Path(output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Capture screenshot with fallback
            try:
                await page.screenshot(
                    path=str(out_path.absolute()),
                    full_page=True,
                    timeout=15000,
                    type="png"
                )
            except Exception as ss_err:
                logger.warning(f"Verification full-page screenshot timed out, capturing viewport: {ss_err}")
                await page.screenshot(
                    path=str(out_path.absolute()),
                    full_page=False,
                    timeout=10000,
                    type="png"
                )
            logger.info(f"  ✓ Saved verification screenshot to {out_path.absolute()}")
            
        except Exception as e:
            logger.error(f"Failed to capture verification screenshot: {e}")
        finally:
            await browser.close()
            
    return output_path
