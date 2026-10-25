#!/usr/bin/env python3
"""
OmniSight — Quick Start Script
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sets up the development environment and starts the backend server.
Usage: python scripts/start_dev.py
"""

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Set up and start the OmniSight development server."""
    project_root = Path(__file__).resolve().parent.parent

    # Check for .env file
    env_file = project_root / ".env"
    env_example = project_root / ".env.example"

    if not env_file.exists():
        print("⚠️  No .env file found. Copying from .env.example...")
        if env_example.exists():
            import shutil
            shutil.copy(env_example, env_file)
            print("✅ Created .env — please update it with your API keys.")
        else:
            print("❌ .env.example not found either!")
            sys.exit(1)

    # Start uvicorn
    print("\n🚀 Starting OmniSight backend server...")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
        ],
        cwd=str(project_root),
    )


if __name__ == "__main__":
    main()
