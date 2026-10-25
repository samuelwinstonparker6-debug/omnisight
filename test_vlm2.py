import asyncio
import sys
sys.path.append('.')
from backend.services.vlm.analyzer import analyze_screenshot
async def main():
  res = await analyze_screenshot('C:/Users/DELL/.gemini/antigravity-ide/brain/8de7f168-b3d4-4690-89f6-94b0d6969eed/.user_uploaded/media_1791640127587.png', 'https://example.com', model='gemini-1.5-pro-latest')
  print(res)
asyncio.run(main())
