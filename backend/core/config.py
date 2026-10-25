"""
OmniSight — Application Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Centralized configuration management using pydantic-settings.
All environment variables are loaded from .env file and validated
at startup with type checking and sensible defaults.
"""

import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict



class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All values can be overridden via a `.env` file in the project root
    or by setting the corresponding environment variable directly.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    app_name: str = "OmniSight"
    app_version: str = "0.1.0"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False

    # ── Logging ──────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # ── Gemini / VLM ────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"

    # ── GitHub ───────────────────────────────────────────────
    github_token: str = ""
    github_repo: str = ""
    github_webhook_secret: str = ""

    # ── Agent ────────────────────────────────────────────────
    max_fix_retries: int = 3

    # ── Target Application ───────────────────────────────────
    staging_url: str = "http://localhost:8000/mock-app/index.html"

    # ── Database ─────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./omnisight.db"

    # ── Browser / Playwright ─────────────────────────────────
    browser_headless: bool = True
    browser_viewport_width: int = 1280
    browser_viewport_height: int = 720

    @property
    def is_gemini_configured(self) -> bool:
        """Check if Gemini API key is set."""
        return bool(self.gemini_api_key)

    @property
    def is_github_configured(self) -> bool:
        """Check if GitHub token is set."""
        return bool(
            self.github_token
            and self.github_token != "ghp_your-github-token-here"
        )

    def set_github_credentials(self, token: str, repo: str = "") -> None:
        """Update GitHub credentials at runtime and persist to .env."""
        self.github_token = token.strip()
        if repo:
            self.github_repo = repo.strip()
        
        # Persist to .env file
        env_path = os.path.join(os.getcwd(), ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                new_lines = []
                token_written = False
                repo_written = False
                for line in lines:
                    if line.startswith("GITHUB_TOKEN="):
                        new_lines.append(f"GITHUB_TOKEN={self.github_token}\n")
                        token_written = True
                    elif line.startswith("GITHUB_REPO=") and self.github_repo:
                        new_lines.append(f"GITHUB_REPO={self.github_repo}\n")
                        repo_written = True
                    else:
                        new_lines.append(line)
                if not token_written:
                    new_lines.append(f"GITHUB_TOKEN={self.github_token}\n")
                if not repo_written and self.github_repo:
                    new_lines.append(f"GITHUB_REPO={self.github_repo}\n")
                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Could not persist to .env: {e}")


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings singleton.

    Uses lru_cache to ensure settings are loaded only once
    and reused across the application lifecycle.

    Returns:
        Settings: Validated application settings instance.
    """
    return Settings()

