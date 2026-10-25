import asyncio
from playwright.async_api import async_playwright

css = """
:root {
  --color-primary: #ffffff;
  --color-accent: #38bdf8;
  --color-text-muted: #94a3b8;
}

h1, h2, h3, h4, h5, h6,
.section-title,
.heading,
[id*="heading"],
.text-gradient,
.hero-title,
.stack-title,
.project-title {
  color: var(--color-primary) !important;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.4);
  background: none !important;
  -webkit-background-clip: initial !important;
  -webkit-text-fill-color: initial !important;
}

h1:is(:not([class])), 
h2:is(:not([class])),
section h2,
.section-heading,
.font-bold {
  color: #ffffff !important;
  letter-spacing: -0.025em;
  font-weight: 800;
  transition: color 0.3s ease;
}

p, span, li {
  color: #cbd5e1;
}

h1:hover, h2:hover, h3:hover {
  color: var(--color-accent) !important;
}
"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.goto("https://samuelwinstonparker6-debug.github.io/Portfolio/", wait_until="domcontentloaded", timeout=15000)
        
        # Scroll to section 1: About / Engineer, Problem-Solver, Builder
        await page.evaluate("window.scrollTo(0, 950)")
        await asyncio.sleep(0.5)
        await page.screenshot(path="output/section1_before.png", animations="disabled")
        
        await page.add_style_tag(content=css)
        await asyncio.sleep(0.5)
        await page.screenshot(path="output/section1_after.png", animations="disabled")
        
        # Scroll to section 2: Core Technical Stack
        await page.evaluate("window.scrollTo(0, 1850)")
        await asyncio.sleep(0.5)
        await page.screenshot(path="output/section2_after.png", animations="disabled")
        
        print("Captured section comparison screenshots!")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
