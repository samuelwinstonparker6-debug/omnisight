# OmniSight

**Multimodal UI Self-Healing & RPA Agent**

OmniSight is an intelligent agent designed to automatically scan web applications, detect visual and layout bugs using Vision-Language Models (VLMs), generate code fixes, and submit Pull Requests directly to your repository.

## Architecture

![Architecture](docs/architecture.md)

1. **Browser Automation**: Uses Playwright to navigate to target URLs and capture full-page screenshots across multiple viewports (desktop, tablet, mobile).
2. **VLM Analysis**: Sends screenshots to a Vision-Language Model (like Gemini) to detect layout bugs, contrast issues, overlapping elements, and accessibility violations.
3. **Agent Orchestrator**: Uses a LangChain-based ReAct agent to orchestrate the pipeline and generate CSS/HTML fixes based on the VLM's analysis.
4. **GitHub PR Creator**: Commits the generated fixes to a new branch and automatically opens a Pull Request on the target repository.

## Project Structure

- `backend/`: FastAPI server for triggering scans and viewing results.
  - `services/browser/`: Playwright automation.
  - `services/vlm/`: Gemini Vision integration.
  - `services/agent/`: LangChain orchestration.
  - `services/github/`: PyGithub PR integration.
- `mock-app/`: A sample e-commerce application with deliberate UI bugs for testing the agent.
- `frontend/`: Premium React/Vite dashboard with real-time scan polling and visual PR preview.
- `tests/`: Unit and integration test suite.

## Setup Instructions

1. Clone the repository.
2. Ensure you have Python 3.10+ installed.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the environment variables template and configure your keys:
   ```bash
   cp .env.example .env
   ```
   Add your `GEMINI_API_KEY` and `GITHUB_TOKEN` to the `.env` file.
5. Start the development server:
   ```bash
   python scripts/start_dev.py
   ```

## Development (15-Day Internship Plan)

This project is being built over a 15-day internship. 
- **Day 1**: Project structure, scaffolding, and mock target application.
- **Day 2-3**: Browser automation & VLM integration.
- **Day 4**: Database persistence.
- **Day 5-6**: Agent orchestration.
- **Day 7**: GitHub PR integration.
- *(Remaining days detailed in project specification)*
