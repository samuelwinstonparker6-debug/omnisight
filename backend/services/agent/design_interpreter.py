"""
OmniSight — Design Studio Interpreter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Classifies user design prompts into one of two modes:
  - "design"   → creative / structural changes (CSS, HTML, layout)
  - "bugfix"   → detect UI issues and fix them (reuses OmniSight VLM pipeline)
  - "both"     → run bug detection first, then apply requested design changes

Then converts the prompt into a structured list of edit actions that can be
applied to files in the target GitHub repository.
"""

import logging
import re
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Intent classification keywords
# ─────────────────────────────────────────────────────────────
_BUG_KEYWORDS = [
    "fix bug", "fix the bug", "detect bug", "find bug", "ui bug",
    "broken", "glitch", "contrast issue", "visibility issue", "overlap",
    "clipped", "overflow", "misaligned", "misalignment", "regression",
    "accessibility", "wcag", "low contrast", "blurred", "washed out",
    "fix the issue", "find issues", "detect issues", "fix issues", "repair",
]

_DESIGN_KEYWORDS = [
    "redesign", "change the", "make the", "add a", "remove the", "update the",
    "style", "color", "layout", "font", "animation", "glassmorphism", "dark mode",
    "theme", "gradient", "hero", "nav", "sidebar", "card", "button", "padding",
    "margin", "spacing", "responsive", "mobile", "tablet", "fullwidth", "full-width",
    "background", "border", "shadow", "rounded", "modern", "aesthetic", "ui update",
    "ui change", "design change",
]


def classify_intent(prompt: str) -> str:
    """
    Returns 'design', 'bugfix', or 'both' based on the prompt content.
    """
    lower = prompt.lower()
    has_bug = any(kw in lower for kw in _BUG_KEYWORDS)
    has_design = any(kw in lower for kw in _DESIGN_KEYWORDS)

    if has_bug and has_design:
        return "both"
    if has_bug:
        return "bugfix"
    return "design"


# ─────────────────────────────────────────────────────────────
# System prompt for action-mapping
# ─────────────────────────────────────────────────────────────
_INTERPRETER_SYSTEM = """\
You are the OmniSight Design Studio Interpreter — an expert front-end engineer \
and UI/UX architect. The user gives you a natural-language design instruction \
for a web page.

Your job is to produce a structured JSON action plan that describes exactly \
what code changes need to be made. Output ONLY a valid JSON object like this:

{
  "summary": "One-line summary of the overall change",
  "intent": "design | bugfix | both",
  "actions": [
    {
      "type": "modify_css",
      "selector": ".hero-title",
      "properties": { "color": "#ffffff", "font-size": "2.5rem" },
      "description": "Make hero title larger and white"
    },
    {
      "type": "add_html_element",
      "parent_selector": "nav",
      "html": "<button id='dark-mode-toggle'>🌙</button>",
      "description": "Add dark mode toggle button to navbar"
    },
    {
      "type": "modify_html_attribute",
      "selector": ".hero-section",
      "attribute": "class",
      "value": "hero-section fullscreen",
      "description": "Add fullscreen class to hero"
    },
    {
      "type": "inject_css_block",
      "css": ".card { backdrop-filter: blur(12px); }",
      "description": "Glassmorphism card effect"
    },
    {
      "type": "modify_js",
      "description": "Add smooth scroll behaviour",
      "code": "document.querySelector('a[href]').addEventListener('click', e => { ... });"
    }
  ],
  "css_patch": "/* Full CSS block that can be injected as-is */",
  "files_affected": ["styles.css", "index.html"]
}

Rules:
1. ALWAYS output ONLY valid JSON — no markdown fences, no prose, no extra keys.
2. Keep selectors surgical and specific — never use blanket selectors like *, body, h1.
3. css_patch must be a self-contained, valid CSS string ready to append to stylesheet.
4. If the prompt mentions bugs, include a bugfix action type: {"type":"run_bug_detection"}.
5. Prefer CSS changes over HTML changes where possible.
6. Maximum 8 actions per plan.
"""


async def interpret_prompt(prompt: str, target_url: str = "", page_source: str = "") -> dict[str, Any]:
    """
    Calls the Gemini LLM to classify the prompt and produce a structured action plan.

    Returns a dict with:
      - intent: "design" | "bugfix" | "both"
      - summary: str
      - actions: list of action dicts
      - css_patch: str (ready-to-inject CSS)
      - files_affected: list[str]
      - raw_response: str (raw LLM output for debugging)
    """
    settings = get_settings()

    # Fast-path fallback if Gemini not configured
    if not settings.gemini_api_key:
        intent = classify_intent(prompt)
        return {
            "intent": intent,
            "summary": prompt[:80],
            "actions": [{"type": "inject_css_block", "css": "", "description": prompt}],
            "css_patch": "",
            "files_affected": ["styles.css"],
            "raw_response": "",
        }

    context_parts = [f"Design instruction: {prompt.strip()}"]
    if target_url:
        context_parts.append(f"Target URL: {target_url}")
    if page_source:
        # Provide a compressed snippet of the HTML for selector context
        snippet = page_source[:3000].strip()
        context_parts.append(f"Page HTML (first 3000 chars):\n```html\n{snippet}\n```")

    user_msg = "\n\n".join(context_parts)

    try:
        llm = ChatGoogleGenerativeAI(
            model=settings.gemini_model or "gemini-1.5-flash",
            google_api_key=settings.gemini_api_key,
            temperature=0.3,
            max_output_tokens=4096,
        )
        messages = [SystemMessage(content=_INTERPRETER_SYSTEM), HumanMessage(content=user_msg)]
        response = await llm.ainvoke(messages)

        raw = response.content
        if isinstance(raw, list):
            raw = "".join(
                item if isinstance(item, str) else (item.get("text", "") if isinstance(item, dict) else str(item))
                for item in raw
            )
        raw = raw.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines).strip()

        import json
        plan = json.loads(raw)

        # Ensure required keys exist
        plan.setdefault("intent", classify_intent(prompt))
        plan.setdefault("summary", prompt[:80])
        plan.setdefault("actions", [])
        plan.setdefault("css_patch", "")
        plan.setdefault("files_affected", ["styles.css"])
        plan["raw_response"] = raw

        logger.info(
            "Design interpreter: intent=%s, actions=%d, files=%s",
            plan["intent"], len(plan["actions"]), plan["files_affected"],
        )
        return plan

    except Exception as e:
        logger.exception("Design interpreter failed: %s", e)
        # Return a safe fallback so the pipeline can still attempt CSS generation
        return {
            "intent": classify_intent(prompt),
            "summary": prompt[:80],
            "actions": [{"type": "inject_css_block", "css": "", "description": prompt}],
            "css_patch": "",
            "files_affected": ["styles.css"],
            "raw_response": str(e),
            "error": str(e),
        }
