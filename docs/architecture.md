# OmniSight Architecture

## High-Level Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Mock App      │     │  React Dashboard │     │  GitHub          │
│   (Bug Target)  │     │  (Frontend)      │     │  (PR Creation)   │
└────────┬────────┘     └────────┬─────────┘     └────────▲─────────┘
         │                       │                         │
         ▼                       ▼                         │
┌────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                                 │
│  ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌──────────────────┐ │
│  │ Browser  │→ │ VLM       │→ │ Agent     │→ │ GitHub PR        │ │
│  │ Service  │  │ Analyzer  │  │ Orchestr. │  │ Creator          │ │
│  │(Playwrt) │  │ (Gemini)  │  │(LangChain)│  │ (PyGithub)       │ │
│  └──────────┘  └───────────┘  └───────────┘  └──────────────────┘ │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              SQLite Database (Run History)                   │  │
│  └─────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

## Data Flow

1. **Screenshot Capture** → Playwright navigates to target URL
2. **VLM Analysis** → Gemini Vision analyzes screenshots for bugs
3. **Fix Generation** → LangChain agent generates CSS/HTML fixes
4. **PR Creation** → PyGithub creates a branch and opens a PR
