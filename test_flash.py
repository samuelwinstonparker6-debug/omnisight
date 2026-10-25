import asyncio
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
load_dotenv('.env')
async def main():
  llm = ChatGoogleGenerativeAI(model='gemini-1.5-flash', google_api_key=os.environ['GEMINI_API_KEY'])
  try:
    res = await llm.ainvoke('hello')
    print('Success:', res.content)
  except Exception as e:
    print('Error:', e)
asyncio.run(main())
