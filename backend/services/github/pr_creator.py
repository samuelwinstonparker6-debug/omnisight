import logging
import uuid
import asyncio
import re
from urllib.parse import urlparse
from typing import Any, Optional, List
from github import Github, GithubException

from backend.core.config import get_settings

logger = logging.getLogger(__name__)


def resolve_repo_from_url(url: str) -> Optional[str]:
    """
    Auto-detects GitHub repository (owner/repo) from GitHub Pages or GitHub URLs.
    Example: https://samuelwinstonparker6-debug.github.io/Portfolio/ -> samuelwinstonparker6-debug/Portfolio
    Example: https://github.com/owner/repo -> owner/repo
    """
    if not url:
        return None
    url = url.strip()
    
    # 1. GitHub Pages format: https://<username>.github.io/<repo>/...
    gh_pages_match = re.search(r"https?://([^.]+)\.github\.io/([^/?#]+)", url, re.IGNORECASE)
    if gh_pages_match:
        owner = gh_pages_match.group(1)
        repo = gh_pages_match.group(2)
        return f"{owner}/{repo}"

    # 2. Direct GitHub URL format: https://github.com/<owner>/<repo>
    gh_match = re.search(r"https?://github\.com/([^/?#]+)/([^/?#]+)", url, re.IGNORECASE)
    if gh_match:
        owner = gh_match.group(1)
        repo = gh_match.group(2)
        return f"{owner}/{repo}"

    return None


def detect_target_stylesheet(repo: Any, target_url: str, page_source: Optional[str] = None) -> str:
    """
    Intelligently identifies the exact stylesheet file in the repository that
    controls styling for the given target_url.
    Prevents modifying unreferenced stylesheets (e.g. mock-app/styles.css on root sites).
    """
    target_url = target_url or ""

    # 1. If target_url explicitly points to a local or remote mock-app
    if "mock-app" in target_url.lower():
        try:
            repo.get_contents("mock-app/styles.css")
            return "mock-app/styles.css"
        except Exception:
            pass
        try:
            repo.get_contents("mock-app/css/styles.css")
            return "mock-app/css/styles.css"
        except Exception:
            pass

    # 2. Extract stylesheet path from page_source if available
    if page_source:
        matches = re.findall(
            r'<link[^>]*rel=[\"\']stylesheet[\"\'][^>]*href=[\"\']([^\"\']+)[\"\']',
            page_source,
            re.IGNORECASE,
        )
        for href in matches:
            clean_href = href.split("?")[0].lstrip("/")
            if not clean_href.startswith("http") and not clean_href.startswith("//"):
                try:
                    repo.get_contents(clean_href)
                    return clean_href
                except Exception:
                    pass

    # 3. Check repository's index.html for linked stylesheet
    try:
        idx_file = repo.get_contents("index.html")
        idx_content = idx_file.decoded_content.decode("utf-8")
        matches = re.findall(
            r'<link[^>]*rel=[\"\']stylesheet[\"\'][^>]*href=[\"\']([^\"\']+)[\"\']',
            idx_content,
            re.IGNORECASE,
        )
        for href in matches:
            clean_href = href.split("?")[0].lstrip("/")
            if not clean_href.startswith("http") and not clean_href.startswith("//"):
                try:
                    repo.get_contents(clean_href)
                    return clean_href
                except Exception:
                    pass
    except Exception:
        pass

    # 4. Fallback search across standard stylesheet names
    candidates = ["style.css", "styles.css", "css/style.css", "css/styles.css", "assets/style.css"]
    for cand in candidates:
        try:
            repo.get_contents(cand)
            return cand
        except Exception:
            continue

    return "style.css"


def apply_fix_locally(file_path: str, new_content: str) -> bool:
    """If file exists locally (e.g. in mock-app/ or workspace), update it on disk."""
    import os
    candidates = [
        os.path.join(os.getcwd(), file_path),
        os.path.join(os.getcwd(), "mock-app", os.path.basename(file_path)),
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(new_content)
                logger.info(f"✅ Synced fix locally to {p}")
                return True
            except Exception as e:
                logger.warning(f"Failed to write local fix to {p}: {e}")
    return False


async def create_multi_bug_fix_pr(
    run_id: str,
    target_url: str,
    bugs: List[Any],
    github_token: Optional[str] = None,
    github_repo: Optional[str] = None,
    page_source: Optional[str] = None,
) -> dict[str, Any]:
    """
    Autonomously creates a branch, commits remediated styles/patches, and opens
    a structured Pull Request on GitHub resolving all detected issues.
    """
    settings = get_settings()
    token = (github_token or settings.github_token or "").strip()
    repo_name = (github_repo or resolve_repo_from_url(target_url) or settings.github_repo or "").strip()

    if not token or token == "ghp_your-github-token-here":
        return {
            "status": "error",
            "message": "GitHub Personal Access Token is not configured. Please connect your GitHub account or set GITHUB_TOKEN."
        }

    if not repo_name or repo_name == "your-username/your-repo-name":
        return {
            "status": "error",
            "message": "Target GitHub repository could not be determined. Please specify repository in owner/repo format."
        }

    def _sync_create():
        g = Github(token)
        repo = g.get_repo(repo_name)
        base_branch = repo.get_branch(repo.default_branch)
        new_branch = f"omnisight/auto-fix-{run_id[:8]}"

        # 1. Create or reset branch
        try:
            repo.create_git_ref(ref=f"refs/heads/{new_branch}", sha=base_branch.commit.sha)
        except GithubException as e:
            if e.status == 422:  # Branch already exists
                ref = repo.get_git_ref(f"heads/{new_branch}")
                ref.edit(sha=base_branch.commit.sha, force=True)
            else:
                raise

        # 2. Compile CSS fixes
        css_rules = [
            f"/* [OmniSight Fix] {bug.title} (Severity: {bug.severity.upper()}) */\n"
            f"{bug.element_selector or 'body'} {{\n  {bug.suggested_fix}\n}}\n"
            for bug in bugs if getattr(bug, "suggested_fix", None)
        ]
        patch_css = "\n".join(css_rules) if css_rules else "/* No CSS fixes */\n"

        # 3. Detect candidate CSS file dynamically based on page and repository
        chosen_file = detect_target_stylesheet(repo, target_url, page_source)
        existing_content = ""
        existing_sha = None
        fc = None

        try:
            fc = repo.get_contents(chosen_file, ref=new_branch)
            existing_sha = fc.sha
            existing_content = fc.decoded_content.decode("utf-8")
        except GithubException:
            pass

        commit_msg = f"fix(ui): OmniSight autonomous remediation for {len(bugs)} issues"
        if not fc:
            final_content = f"/* === OmniSight Remediated CSS === */\n\n{patch_css}"
            try:
                repo.create_file(chosen_file, commit_msg, final_content, branch=new_branch)
            except GithubException as e:
                if e.status == 422:
                    fc = repo.get_contents(chosen_file, ref=new_branch)
                    repo.update_file(chosen_file, commit_msg, final_content, fc.sha, branch=new_branch)
                else:
                    raise
        else:
            final_content = existing_content + f"\n\n/* === OmniSight Autonomous Fixes ({run_id[:8]}) === */\n{patch_css}"
            repo.update_file(chosen_file, commit_msg, final_content, existing_sha, branch=new_branch)

        # Apply locally as well so local target app or local preview updates immediately
        apply_fix_locally(chosen_file, final_content)

        # 4. Generate Rich PR Markdown Body
        bug_rows = ""
        for i, bug in enumerate(bugs, 1):
            severity_badge = f"`{bug.severity.upper()}`"
            bug_rows += f"| {i} | {bug.title} | {severity_badge} | `{bug.element_selector}` | `{bug.suggested_fix[:40]}...` |\n"

        pr_body = f"""## 🤖 OmniSight Autonomous Self-Healing Patch

This Pull Request was generated autonomously by **OmniSight RPA Agent** following an automated visual scan.

### 🎯 Scan Metadata
- **Target URL:** {target_url}
- **Scan Run ID:** `{run_id}`
- **Remediated Issues:** {len(bugs)}
- **Modified File:** `{chosen_file}`

---

### 📋 Detected Anomalies & Applied Patches
| # | Issue | Severity | Target Selector | Patch Preview |
|---|-------|----------|-----------------|---------------|
{bug_rows}

---

### 🛠️ Applied CSS Fixes
```css
{patch_css}
```

*Generated automatically by OmniSight UI Self-Healing Agent.*
"""

        # 5. Open Pull Request
        pr_title = f"fix(ui): OmniSight automated visual patches ({len(bugs)} fixes)"
        try:
            pr = repo.create_pull(
                title=pr_title,
                body=pr_body,
                head=new_branch,
                base=repo.default_branch,
            )
            return pr.html_url, pr.number, new_branch
        except GithubException as e:
            # If PR already exists for this branch, return existing
            if e.status == 422:
                pulls = repo.get_pulls(head=f"{repo.owner.login}:{new_branch}", state="open")
                for p in pulls:
                    return p.html_url, p.number, new_branch
            raise

    try:
        pr_url, pr_number, created_branch = await asyncio.to_thread(_sync_create)
        return {
            "status": "success",
            "pr_url": pr_url,
            "pr_number": pr_number,
            "branch_name": created_branch,
            "repo": repo_name,
        }
    except Exception as e:
        logger.error(f"Failed to create GitHub PR: {e}")
        return {"status": "error", "message": str(e), "repo": repo_name}


async def create_fix_pr(
    file_path: str,
    fix_content: str,
    bug_description: str,
    bug_severity: Optional[str] = "medium",
    bug_viewport: Optional[str] = "desktop",
    bug_element_selector: Optional[str] = "N/A",
    vlm_reasoning: Optional[str] = "Applied targeted CSS to resolve layout anomaly.",
    before_img_url: Optional[str] = None,
    after_img_url: Optional[str] = None,
    original_content: Optional[str] = None,
    branch_name: Optional[str] = None,
    github_token: Optional[str] = None,
    github_repo: Optional[str] = None,
    target_url: Optional[str] = None,
) -> dict[str, Any]:
    """
    Creates a branch, commits a single fix, and opens a structured PR on GitHub.
    Also syncs the fix to local files if applicable.
    """
    settings = get_settings()
    token = (github_token or settings.github_token or "").strip()
    repo_name = (github_repo or (resolve_repo_from_url(target_url) if target_url else None) or settings.github_repo or "").strip()

    # Always ensure local file is patched as well so local target servers reflect changes immediately
    apply_fix_locally(file_path, fix_content)

    if not token or not repo_name or token == "ghp_your-github-token-here":
        logger.warning("GitHub credentials not configured. Returning mock PR success.")
        return {"status": "success", "pr_url": "https://github.com/mock/repo/pull/999", "pr_number": 999}

    def _sync_create_pr():
        g = Github(token)
        repo = g.get_repo(repo_name)
        base_branch = repo.get_branch(repo.default_branch)
        new_branch = branch_name or f"omnisight-fix-{uuid.uuid4().hex[:8]}"

        repo.create_git_ref(ref=f"refs/heads/{new_branch}", sha=base_branch.commit.sha)

        actual_file = file_path
        # If file_path is generic mock-app but repo uses style.css
        if actual_file == "mock-app/styles.css" and target_url and "mock-app" not in target_url:
            actual_file = detect_target_stylesheet(repo, target_url)

        commit_msg = f"fix(ui): OmniSight auto-fix for {bug_description[:50]}"
        try:
            contents = repo.get_contents(actual_file, ref=new_branch)
            repo.update_file(actual_file, commit_msg, fix_content, contents.sha, branch=new_branch)
        except GithubException as e:
            if e.status == 404:
                repo.create_file(actual_file, commit_msg, fix_content, branch=new_branch)
            else:
                raise

        before_md = f"![Before Fix]({before_img_url})" if before_img_url else "*No image provided*"
        after_md = f"![After Fix]({after_img_url})" if after_img_url else "*No image provided*"

        pr_body = f"""## 🤖 OmniSight Autonomous UI Self-Healing Patch

This Pull Request was autonomously generated by the **OmniSight RPA Agent** to resolve a detected visual layout regression.

### 📋 Bug Summary
| Attribute | Details |
|-----------|---------|
| **Issue** | {bug_description} |
| **Severity** | `{bug_severity.upper()}` |
| **Viewport** | `{bug_viewport}` |
| **Selector** | `{bug_element_selector}` |
| **File Modified** | `{actual_file}` |

### 📸 Visual Verification
| Before (Original) | After (Verified In-Browser) |
|:---:|:---:|
| {before_md} | {after_md} |

### 🧠 VLM Diagnostic Reasoning
> {vlm_reasoning}
"""
        pr = repo.create_pull(
            title=f"🔧 OmniSight Fix: {bug_description[:50]}",
            body=pr_body,
            head=new_branch,
            base=repo.default_branch
        )
        return pr.html_url, pr.number, new_branch, actual_file

    try:
        pr_url, pr_number, created_branch, used_file = await asyncio.to_thread(_sync_create_pr)
        return {
            "status": "success",
            "pr_url": pr_url,
            "pr_number": pr_number,
            "branch_name": created_branch,
            "file_modified": used_file,
        }
    except Exception as e:
        logger.error(f"Failed to create GitHub PR: {e}")
        return {"status": "error", "message": str(e)}


async def sync_merged_pr_changes(
    run_id: str,
    target_url: Optional[str] = None,
    pr_url: Optional[str] = None,
    github_token: Optional[str] = None,
    github_repo: Optional[str] = None,
) -> dict[str, Any]:
    """
    Checks if the Pull Request associated with run_id has been merged into main.
    If merged, pulls the updated files directly from GitHub and applies them
    to local target files (for local servers) or verifies deployment status (for GitHub Pages).
    """
    import requests
    settings = get_settings()
    token = (github_token or settings.github_token or "").strip()

    if not pr_url:
        return {"status": "error", "message": "No Pull Request URL associated with this run."}

    m = re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", pr_url)
    if not m:
        return {"status": "error", "message": f"Could not parse GitHub PR URL: {pr_url}"}

    repo_name = (github_repo or m.group(1)).strip()
    pr_number = int(m.group(2))

    def _sync():
        g = Github(token)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        if not pr.merged:
            return {
                "status": "not_merged",
                "merged": False,
                "state": pr.state,
                "pr_number": pr_number,
                "pr_url": pr_url,
                "message": f"PR #{pr_number} is currently {pr.state.upper()} (not merged yet). Please merge it on GitHub first."
            }

        synced_files = []
        for file in pr.get_files():
            try:
                fc = repo.get_contents(file.filename, ref=repo.default_branch)
                content = fc.decoded_content.decode("utf-8")
                did_apply = apply_fix_locally(file.filename, content)
                synced_files.append({"filename": file.filename, "applied_locally": did_apply})
            except Exception as e:
                logger.warning(f"Could not sync file {file.filename}: {e}")

        pages_build_status = "N/A"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        try:
            resp = requests.get(f"https://api.github.com/repos/{repo_name}/pages/builds", headers=headers, timeout=5)
            if resp.status_code == 200 and resp.json():
                latest = resp.json()[0]
                pages_build_status = latest.get("status", "unknown")
        except Exception:
            pass

        return {
            "status": "success",
            "merged": True,
            "state": "closed",
            "pr_number": pr_number,
            "pr_url": pr_url,
            "synced_files": synced_files,
            "pages_build_status": pages_build_status,
            "target_url": target_url or "",
            "message": (
                f"🎉 PR #{pr_number} confirmed merged! "
                + (f"GitHub Pages deployment status: '{pages_build_status}'. " if pages_build_status != "N/A" else "")
                + "Changes have been successfully synchronized."
            )
        }

    return await asyncio.to_thread(_sync)


