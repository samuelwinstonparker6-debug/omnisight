import os
import logging
import asyncio
from backend.core.config import get_settings
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

async def generate_fixed_code(source_code: str, bugs: list[dict]) -> str:
    """
    Takes the original source HTML and the list of detected bugs,
    and asks the LLM to rewrite the HTML to fix them.
    """
    settings = get_settings()
    # Prepare surgical CSS fix overrides based only on specific detected UI bugs
    css_patches = []
    forbidden_selectors = {"*", "body", "html", "p", "span", "div", "a", "button", "input", "select", "h1", "h2", "h3"}
    for b in bugs:
        selector = (b.get("element_selector") or "").strip()
        fix = (b.get("suggested_fix") or "").strip()
        
        # Guardrail: skip blanket or destructive selectors
        if not selector or selector in forbidden_selectors:
            continue
        if fix:
            css_patches.append(f"/* Bug Fix: {b.get('title', 'UI Fix')} */\n{selector} {{\n  {fix}\n}}")
            
    patch_style = "\n<style id='omnisight-ai-fixes'>\n" + "\n\n".join(css_patches) + "\n</style>\n"

    # If Gemini API key is configured, ask gemini-2.5-pro for surgical CSS rules
    if settings.gemini_api_key and bugs:
        try:
            llm = ChatGoogleGenerativeAI(
                model=settings.gemini_model or "gemini-3.6-flash",
                google_api_key=settings.gemini_api_key,
                temperature=0.1,
                request_timeout=15.0,
            )
            bugs_text = "\n".join([
                f"- Selector: {b.get('element_selector', 'unknown')} | Title: {b.get('title', '')} | Issue: {b.get('description', '')} | Suggested: {b.get('suggested_fix', '')}"
                for b in bugs[:6]
            ])
            prompt = f"""You are a principal CSS engineer performing surgical, non-destructive bug fixes on a website.
Detected UI Bugs:
{bugs_text}

Rules:
1. Output ONLY valid CSS rules to resolve these bugs.
2. DO NOT use blanket tags (never style `*`, `body`, `h1, h2, h3`, `p`, `button`, etc. directly).
3. DO NOT delete existing gradients or artwork (never output `background: none !important`).
4. Keep overrides minimal (max 2-3 properties per selector).
5. Output ONLY raw CSS, no markdown fences (no ```css), no HTML tags.
"""
            async with asyncio.timeout(15.0):
                response = await llm.ainvoke(prompt)
                ai_css = response.content
                if isinstance(ai_css, list):
                    ai_css = "".join(
                        item if isinstance(item, str) else (item.get("text", "") if isinstance(item, dict) else str(item))
                        for item in ai_css
                    )
                elif not isinstance(ai_css, str):
                    ai_css = str(ai_css or "")
                ai_css = ai_css.strip()
                if ai_css.startswith("```"):
                    lines = ai_css.splitlines()
                    if lines[0].startswith("```"): lines = lines[1:]
                    if lines and lines[-1].strip().startswith("```"): lines = lines[:-1]
                    ai_css = "\n".join(lines)
                if len(ai_css) > 10:
                    patch_style = f"\n<style id='omnisight-ai-fixes'>\n{ai_css}\n</style>\n"
        except Exception as e:
            logger.warning(f"AI surgical CSS generation fallback: {e}. Using deterministic patches.")

    # Inject surgical style tag into full source code preserving 100% of the original page
    if "</head>" in source_code:
        return source_code.replace("</head>", f"{patch_style}</head>")
    elif "</body>" in source_code:
        return source_code.replace("</body>", f"{patch_style}</body>")
    else:
        return patch_style + "\n" + source_code

