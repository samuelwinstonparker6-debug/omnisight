"""
OmniSight — Pydantic Data Models
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Structured data models for API requests/responses, scan results,
bug reports, and pipeline configuration.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl


# ── Enums ────────────────────────────────────────────────────


class BugSeverity(str, Enum):
    """Severity level of a detected UI bug."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class BugCategory(str, Enum):
    """Category of a detected UI bug."""

    LAYOUT = "layout"
    CONTRAST = "contrast"
    OVERFLOW = "overflow"
    OVERLAP = "overlap"
    RESPONSIVE = "responsive"
    ACCESSIBILITY = "accessibility"
    TYPOGRAPHY = "typography"
    INTERACTION = "interaction"
    OTHER = "other"


class ScanStatus(str, Enum):
    """Status of a scan run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Bug Report ───────────────────────────────────────────────


class BugReport(BaseModel):
    """A single UI bug detected by the VLM."""

    id: str = Field(..., description="Unique bug identifier")
    category: BugCategory = Field(..., description="Bug category")
    severity: BugSeverity = Field(..., description="Bug severity level")
    title: str = Field(..., description="Short bug title", max_length=200)
    description: str = Field(..., description="Detailed bug description")
    element_selector: Optional[str] = Field(None, description="CSS selector of affected element")
    viewport: str = Field(..., description="Viewport where bug was detected")
    screenshot_path: Optional[str] = Field(None, description="Path to annotated screenshot")
    suggested_fix: Optional[str] = Field(None, description="Suggested CSS/HTML fix")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence score")
    verification_status: Optional[str] = Field(None, description="Verification status (verified_fixed / still_broken)")
    verification_screenshot_path: Optional[str] = Field(None, description="Path to verification screenshot")


# ── Scan Request / Response ──────────────────────────────────


class ScanRequest(BaseModel):
    """Request payload for triggering a UI scan."""

    url: Optional[str] = Field(None, description="Target URL (defaults to STAGING_URL)")
    viewports: list[str] = Field(
        default=["desktop", "tablet", "mobile"],
        description="Viewport sizes to scan",
    )
    auto_fix: bool = Field(False, description="Automatically generate fix suggestions")
    create_pr: bool = Field(False, description="Create a GitHub PR with fixes")
    model: Optional[str] = Field(None, description="VLM model to use (e.g. gemini-2.5-pro, gemini-3.8-flash)")
    prompt: Optional[str] = Field(None, description="Custom prompt / pre-loaded directives for visual bug scan")



class ScanResult(BaseModel):
    """Result of a completed UI scan."""

    run_id: str = Field(..., description="Unique run identifier")
    url: str = Field(..., description="Scanned URL")
    status: ScanStatus = Field(..., description="Scan status")
    started_at: datetime = Field(..., description="Scan start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Scan completion timestamp")
    duration_seconds: Optional[float] = Field(None, description="Scan duration in seconds")
    bugs: list[BugReport] = Field(default_factory=list, description="Detected bugs")
    total_bugs: int = Field(0, description="Total number of bugs found")
    screenshots: dict[str, str] = Field(
        default_factory=dict,
        description="Viewport → screenshot path mapping",
    )
    pr_url: Optional[str] = Field(None, description="GitHub PR URL if created")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class GitHubConnectRequest(BaseModel):
    """Payload to connect GitHub token and optional repo."""
    token: str = Field(..., description="GitHub Personal Access Token")
    repo: str = Field("", description="Optional owner/repo")

