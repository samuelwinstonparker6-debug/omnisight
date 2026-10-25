import { useState, useEffect } from "react";
import {
  Play,
  Activity,
  CheckCircle,
  XCircle,
  Clock,
  ChevronRight,
  Bug,
  LayoutDashboard,
  Settings,
  Eye,
  Globe,
  RotateCcw,
  Download,
  FileText,
  Copy,
  Check,
  ExternalLink,
  GitPullRequest,
  Key,
  X,
  AlertCircle,
  Wand2,
} from "lucide-react";
import "./index.css";
import DesignStudio from "./DesignStudio";
import SettingsView from "./SettingsView";

const API_BASE = typeof window !== "undefined" && (window.location.port === "5173" || window.location.port === "8000")
  ? "/api/v1"
  : "http://127.0.0.1:8000/api/v1";

function App() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [selectedRun, setSelectedRun] = useState(null);
  const [runDetails, setRunDetails] = useState(null);
  const [actioningBug, setActioningBug] = useState(null);
  const [targetUrl, setTargetUrl] = useState(() => {
    return localStorage.getItem("omnisight_target_url") || "";
  });
  const [bugStatuses, setBugStatuses] = useState({});
  const [scanStage, setScanStage] = useState("");
  const [showPreview, setShowPreview] = useState(false);
  const [showNotepadCode, setShowNotepadCode] = useState(false);
  const [notepadContent, setNotepadContent] = useState("");
  const [copySuccess, setCopySuccess] = useState(false);
  const [downloadSuccessMsg, setDownloadSuccessMsg] = useState("");

  // GitHub Integration state
  const [githubStatus, setGithubStatus] = useState({ configured: false, username: null, repo: "" });
  const [showGithubModal, setShowGithubModal] = useState(false);
  const [githubTokenInput, setGithubTokenInput] = useState("");
  const [githubRepoInput, setGithubRepoInput] = useState("");
  const [connectingGithub, setConnectingGithub] = useState(false);
  const [githubError, setGithubError] = useState("");
  const [creatingPr, setCreatingPr] = useState(false);
  const [prResult, setPrResult] = useState(null);
  const [syncingPr, setSyncingPr] = useState(false);
  const [previewKey, setPreviewKey] = useState(Date.now());
  const [dsAutoRun, setDsAutoRun] = useState(null); // { prompt, runBugScan } — triggers DesignStudio auto-run

  // Instantaneous theme mode state (persisted to localStorage)
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem("omnisight_theme") || "dark";
  });

  const handleThemeChange = (newTheme) => {
    setTheme(newTheme);
    localStorage.setItem("omnisight_theme", newTheme);
    document.documentElement.setAttribute("data-theme", newTheme);
  };

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);


  const normalizeUrl = (rawUrl) => {
    let url = (rawUrl || "").trim();
    if (!url) return "";
    if (!/^https?:\/\//i.test(url)) {
      url = `https://${url}`;
    }
    return url;
  };

  const handleUrlChange = (newVal) => {
    setTargetUrl(newVal);
    localStorage.setItem("omnisight_target_url", newVal);
  };

  const fetchGithubStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/github/status`);
      if (res.ok) {
        const data = await res.json();
        setGithubStatus(data);
        if (data.repo && !githubRepoInput) {
          setGithubRepoInput(data.repo);
        }
      }
    } catch (e) {
      console.error("Failed to fetch github status", e);
    }
  };

  useEffect(() => {
    fetchGithubStatus();
  }, []);

  const handleConnectGithub = async (e) => {
    e?.preventDefault();
    if (!githubTokenInput.trim()) {
      setGithubError("Please paste a valid GitHub Personal Access Token.");
      return;
    }
    setConnectingGithub(true);
    setGithubError("");
    try {
      const res = await fetch(`${API_BASE}/github/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: githubTokenInput, repo: githubRepoInput }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Authentication failed");
      }
      setGithubStatus({ configured: true, username: data.username, repo: data.repo });
      setShowGithubModal(false);
      setDownloadSuccessMsg(`✅ Connected to GitHub as @${data.username}!`);
      setTimeout(() => setDownloadSuccessMsg(""), 6000);
    } catch (err) {
      setGithubError(err.message);
    } finally {
      setConnectingGithub(false);
    }
  };

  const handleCreatePr = async (runId) => {
    if (!runId) return;
    if (!githubStatus.configured) {
      setShowGithubModal(true);
      return;
    }
    setCreatingPr(true);
    setPrResult(null);
    try {
      const res = await fetch(`${API_BASE}/scans/${runId}/create-pr`, { method: "POST" });
      const data = await res.json();
      if (!res.ok || data.status === "error") {
        throw new Error(data.message || data.detail || "Failed to create PR");
      }
      setPrResult(data);
      if (runDetails && runDetails.run_id === runId) {
        setRunDetails(prev => ({ ...prev, pr_url: data.pr_url }));
      }
      setDownloadSuccessMsg(`🚀 Created Pull Request #${data.pr_number} on GitHub! Merge it on GitHub, then click 'Sync Merged PR' to see changes live.`);
      setTimeout(() => setDownloadSuccessMsg(""), 9000);
    } catch (err) {
      alert("Error creating Pull Request: " + err.message);
    } finally {
      setCreatingPr(false);
    }
  };

  const handleSyncPr = async (runId) => {
    if (!runId) return;
    setSyncingPr(true);
    try {
      const res = await fetch(`${API_BASE}/scans/${runId}/sync-pr`, { method: "POST" });
      const data = await res.json();
      if (!res.ok || data.status === "error") {
        throw new Error(data.message || data.detail || "Failed to check PR status");
      }
      if (data.merged) {
        setDownloadSuccessMsg(`🎉 ${data.message}`);
        setPreviewKey(Date.now());
        setTimeout(() => setDownloadSuccessMsg(""), 10000);
      } else {
        alert(data.message);
      }
    } catch (err) {
      alert("Error syncing Pull Request: " + err.message);
    } finally {
      setSyncingPr(false);
    }
  };


  const fetchAndSetNotepadContent = async (runId) => {
    try {
      const res = await fetch(`${API_BASE}/scans/${runId}/omnisight_fixed_code.txt`);
      if (res.ok) {
        const text = await res.text();
        setNotepadContent(text);
      }
    } catch (e) {
      console.error("Failed to load notepad text", e);
    }
  };

  const handleDownloadFix = async (runId) => {
    if (!runId) return;
    const filename = "omnisight_scan_fixes.zip";
    const downloadUrl = `${API_BASE}/scans/${runId}/omnisight_scan_fixes.zip`;
    try {
      // 1. Direct native browser download (Edge/Chrome/Firefox native file stream)
      // Since API is proxied to same-origin (/api/v1), the browser's download manager
      // respects both download attribute and server Content-Disposition header.
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = filename;
      link.setAttribute("download", filename);
      document.body.appendChild(link);
      link.click();
      setTimeout(() => {
        if (link.parentNode) document.body.removeChild(link);
      }, 2000);
      setDownloadSuccessMsg(`✅ Downloaded '${filename}'! You can open it in File Explorer. Also saved to your Downloads folder.`);
      setTimeout(() => setDownloadSuccessMsg(""), 6000);
    } catch (e) {
      console.warn("Direct download failed, attempting blob fallback:", e);
      try {
        const res = await fetch(downloadUrl);
        const blob = await res.blob();
        const file = new File([blob], filename, { type: "application/zip" });
        const blobUrl = window.URL.createObjectURL(file);
        const link = document.createElement("a");
        link.href = blobUrl;
        link.download = filename;
        link.setAttribute("download", filename);
        document.body.appendChild(link);
        link.click();
        // Keep blob valid for 60 seconds so Windows Defender / Edge file manager finishes saving
        setTimeout(() => {
          window.URL.revokeObjectURL(blobUrl);
          if (link.parentNode) document.body.removeChild(link);
        }, 60000);
      } catch (fallbackErr) {
        window.location.href = downloadUrl;
      }
    }
  };

  const handleDownloadTxt = async (runId) => {
    if (!runId) return;
    const filename = "fixed_code.txt";
    const downloadUrl = `${API_BASE}/scans/${runId}/fixed_code.txt`;
    try {
      // 1. Direct native browser download
      // Guarantees Windows saves as a clean .txt file so double-clicking immediately launches Notepad
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = filename;
      link.setAttribute("download", filename);
      document.body.appendChild(link);
      link.click();
      setTimeout(() => {
        if (link.parentNode) document.body.removeChild(link);
      }, 2000);
      setDownloadSuccessMsg(`✅ Downloaded '${filename}'! Double-click in Downloads to open in Windows Notepad.`);
      setTimeout(() => setDownloadSuccessMsg(""), 6000);
    } catch (e) {
      console.warn("Direct download failed, attempting blob fallback:", e);
      try {
        const res = await fetch(downloadUrl);
        const text = await res.text();
        const file = new File([text], filename, { type: "text/plain;charset=utf-8" });
        const blobUrl = window.URL.createObjectURL(file);
        const link = document.createElement("a");
        link.href = blobUrl;
        link.download = filename;
        link.setAttribute("download", filename);
        document.body.appendChild(link);
        link.click();
        // Keep blob valid for 60 seconds
        setTimeout(() => {
          window.URL.revokeObjectURL(blobUrl);
          if (link.parentNode) document.body.removeChild(link);
        }, 60000);
      } catch (fallbackErr) {
        window.location.href = downloadUrl;
      }
    }
  };

  const handleOpenNotepad = async (runId) => {
    if (!runId) return;
    try {
      const res = await fetch(`${API_BASE}/scans/${runId}/open-notepad`, { method: "POST" });
      const data = await res.json();
      setDownloadSuccessMsg("🚀 Opened 'omnisight_fixed_code.txt' in Windows Notepad!");
      setTimeout(() => setDownloadSuccessMsg(""), 6000);
    } catch (e) {
      console.error("Failed to open notepad", e);
    }
  };


  const handleCopyNotepadCode = () => {
    if (!notepadContent) return;
    navigator.clipboard.writeText(notepadContent);
    setCopySuccess(true);
    setTimeout(() => setCopySuccess(false), 2500);
  };

  useEffect(() => {
    fetchRuns();
  }, []);

  const fetchRuns = async () => {
    try {
      const res = await fetch(`${API_BASE}/runs`);
      const data = await res.json();
      const runList = data.runs || [];
      setRuns(runList);

      // Check if any run is currently running (case-insensitive check)
      const activeRun = runList.find(
        (run) =>
          String(run.status).toLowerCase() === "running" ||
          String(run.status).toLowerCase() === "pending"
      );

      const isRunning = Boolean(activeRun);
      setScanning(isRunning);

      if (isRunning && activeRun) {
        if (activeRun.stage) {
          setScanStage(activeRun.stage);
        }
      } else {
        setScanStage("");
      }

      setLoading(false);
    } catch (err) {
      console.error("Failed to fetch runs:", err);
      setLoading(false);
    }
  };

  useEffect(() => {
    // Poll for updates while scanning
    let intervalId;
    if (scanning) {
      intervalId = setInterval(() => {
        fetchRuns();
        if (selectedRun) {
          viewRunDetails(selectedRun);
        }
      }, 1500);
    }
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [scanning, selectedRun]);

  // 2 Pre-loaded prompts for Dashboard visual scan & automated remediation
  const DASHBOARD_PRELOADED_PROMPTS = [
    "Fix any UI bugs and also make the layout full-bleed with more breathing room",
    "Detect and fix all contrast and visibility issues on the page",
  ];

  const triggerScan = async () => {
    const finalUrl = normalizeUrl(targetUrl);
    if (!finalUrl) {
      alert("Please enter a valid target URL to scan.");
      return;
    }
    if (finalUrl !== targetUrl) {
      handleUrlChange(finalUrl);
    }

    // Ensure we stay on Dashboard view (not navigating away to Design Studio)
    setSelectedRun(null);
    setScanning(true);
    setScanStage("Capturing Screenshots...");

    const combinedPrompt = DASHBOARD_PRELOADED_PROMPTS.join(". ");

    try {
      const res = await fetch(`${API_BASE}/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: finalUrl,
          prompt: combinedPrompt,
          auto_fix: true,
          create_pr: true,
        }),
      });

      let data = {};
      const rawText = await res.text();
      try {
        data = rawText ? JSON.parse(rawText) : {};
      } catch (parseErr) {
        console.error("Non-JSON API response:", rawText);
        throw new Error(`Server returned non-JSON response (${res.status} ${res.statusText}): ${rawText.slice(0, 150)}`);
      }

      if (res.ok && data.run_id) {
        setSelectedRun(data.run_id);
        fetchRuns();
      } else {
        alert(`Failed to start scan: ${data.detail || data.message || "Unknown server error"}`);
        setScanning(false);
      }
    } catch (err) {
      console.error("Scan trigger failed:", err);
      alert(`Error starting scan: ${err.message}`);
      setScanning(false);
    }
  };

  const viewRunDetails = async (runId, currentSelected) => {
    if (currentSelected !== runId) {
      setRunDetails(null);
    }
    setSelectedRun(runId);
    try {
      const res = await fetch(`${API_BASE}/runs/${runId}`);
      const data = await res.json();
      setRunDetails(data);
      if (data && (data.status === "COMPLETED" || data.status === "completed")) {
        fetchAndSetNotepadContent(runId);
      } else if (data?.metadata?.stage) {
        setScanStage(data.metadata.stage);
      }
    } catch (err) {
      console.error("Failed to fetch run details:", err);
    }
  };

  const handleBugAction = async (bugId, action) => {
    setActioningBug(bugId);
    try {
      const res = await fetch(`${API_BASE}/bugs/${bugId}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const data = await res.json();

      if (res.ok) {
        setBugStatuses((prev) => ({
          ...prev,
          [bugId]: {
            status: action === "approve" ? "approved" : "rejected",
            prUrl: data.pr_url || null,
          },
        }));
      } else {
        alert(`Failed to ${action} fix: ${data.detail || data.message}`);
      }
    } catch (err) {
      console.error(`Failed to ${action} fix:`, err);
      alert(`Error: Failed to ${action} fix`);
    } finally {
      setActioningBug(null);
    }
  };

  return (
    <div className="app-wrapper">
      <aside className="sidebar">
        <div className="sidebar-logo" onClick={() => setSelectedRun(null)}>
          <div className="sidebar-logo-icon-wrap">
            <span className="cyber-scanner-beam" />
            <Eye size={19} color="#22d3ee" strokeWidth={2.2} />
          </div>
          <span className="sidebar-logo-text">
            <span className="cyber-prefix">//</span>
            <span className="cyber-omni">Omni</span>
            <span className="cyber-sight">Sight</span>
            <span className="cyber-cursor" />
          </span>
        </div>

        <nav style={{ flex: 1 }}>
          <div
            className={`nav-item ${selectedRun === null ? 'active' : ''}`}
            onClick={() => setSelectedRun(null)}
          >
            <LayoutDashboard size={20} />
            Dashboard
          </div>
          <div
            className={`nav-item ${selectedRun === 'design' ? 'active' : ''}`}
            onClick={() => setSelectedRun('design')}
          >
            <Wand2 size={20} />
            Design Studio
          </div>
          <div
            className={`nav-item ${selectedRun === 'settings' ? 'active' : ''}`}
            onClick={() => setSelectedRun('settings')}
          >
            <Settings size={20} />
            Settings
          </div>
        </nav>

        <div
          style={{
            marginTop: "auto",
            padding: "1rem",
            background: "rgba(255,255,255,0.02)",
            borderRadius: "8px",
            fontSize: "0.875rem",
            color: "var(--text-muted)",
            textAlign: "center",
          }}
        >
          v0.1.0-beta
        </div>
      </aside>

      <div className="app-container">
        <header className="header animate-fade-in">
          <div>
            <h1 className="header-title">
              {selectedRun === 'settings' ? 'Settings' : selectedRun === 'design' ? 'AI Design Studio' : 'Dashboard'}
            </h1>
            <p style={{ color: "var(--text-muted)" }}>
              {selectedRun === 'settings'
                ? 'Preferences, visual theme, and system controls'
                : selectedRun === 'design'
                ? 'Autonomous prompt-driven UI restyling & bug elimination'
                : 'Multimodal UI Self-Healing & RPA Agent'}
            </p>
          </div>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <div
              style={{
                position: "relative",
                display: "flex",
                alignItems: "center",
              }}
            >
              <Globe
                size={16}
                color="var(--accent-primary)"
                style={{
                  position: "absolute",
                  left: "0.85rem",
                  pointerEvents: "none",
                }}
              />
              <input
                type="url"
                placeholder="Enter any target URL (e.g. https://example.com)..."
                value={targetUrl}
                onChange={(e) => handleUrlChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !scanning) {
                    triggerScan();
                  }
                }}
                className="input-field"
                style={{
                  padding: "0.75rem 2.25rem 0.75rem 2.4rem",
                  borderRadius: "10px",
                  border: "1px solid var(--border-glass)",
                  background: "rgba(255, 255, 255, 0.08)",
                  color: "var(--text-primary)",
                  width: "380px",
                  outline: "none",
                  fontSize: "0.875rem",
                  letterSpacing: "0.01em",
                  transition: "border-color 0.2s, box-shadow 0.2s, background 0.2s",
                }}
                onFocus={(e) => {
                  e.target.style.borderColor = "var(--accent-primary)";
                  e.target.style.boxShadow = "0 0 12px var(--accent-glow)";
                  e.target.style.background = "rgba(255, 255, 255, 0.12)";
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = "var(--border-glass)";
                  e.target.style.boxShadow = "none";
                  e.target.style.background = "rgba(255, 255, 255, 0.08)";
                }}
              />
              {targetUrl && (
                <button
                  type="button"
                  onClick={() => handleUrlChange("")}
                  title="Clear URL"
                  style={{
                    position: "absolute",
                    right: "0.75rem",
                    background: "none",
                    border: "none",
                    color: "var(--text-muted)",
                    cursor: "pointer",
                    fontSize: "1rem",
                    padding: "0.2rem",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                  onMouseOver={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
                  onMouseOut={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
                >
                  ✕
                </button>
              )}
            </div>
            <button
              className="btn btn-primary"
              onClick={triggerScan}
              disabled={scanning}
              title="Runs autonomous UI bug detection on dashboard with pre-loaded prompts: UI layout & contrast/visibility remediation"
              style={{
                padding: "0.75rem 1.25rem",
                borderRadius: "10px",
                fontWeight: 500,
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                boxShadow: "0 4px 12px rgba(99, 102, 241, 0.25)",
                cursor: scanning ? "not-allowed" : "pointer",
                opacity: scanning ? 0.7 : 1,
              }}
            >
              <Play size={18} />
              {scanning ? "Scanning..." : "Scan URL"}
            </button>

            <div
              className={`github-badge ${githubStatus.configured ? "connected" : "disconnected"}`}
              onClick={() => setShowGithubModal(true)}
              title={
                githubStatus.configured
                  ? `Connected to GitHub as @${githubStatus.username}. Click to manage.`
                  : "Click to connect your GitHub account for 1-click PRs."
              }
            >
              <GitPullRequest size={15} />
              <span>{githubStatus.configured ? `@${githubStatus.username}` : "Connect GitHub"}</span>
            </div>
          </div>
        </header>

        {/* ── Settings View ── */}
        {selectedRun === 'settings' && (
          <main style={{ padding: "1.5rem", overflowY: "auto" }}>
            <SettingsView theme={theme} onThemeChange={handleThemeChange} />
          </main>
        )}

        {/* ── AI Design Studio View ── */}
        {selectedRun === 'design' && (
          <main style={{ padding: "1.5rem", overflowY: "auto" }}>
            <DesignStudio
              githubStatus={githubStatus}
              onConnectGithub={() => setShowGithubModal(true)}
              targetUrl={targetUrl}
              autoRun={dsAutoRun}
              onAutoRunConsumed={() => setDsAutoRun(null)}
            />
          </main>
        )}

        {selectedRun !== 'design' && selectedRun !== 'settings' && (
          <main className="grid grid-cols-3">
          {/* Pipeline Progress Indicator */}
          {scanning && (
            <div
              className="glass-panel animate-fade-in"
              style={{
                gridColumn: "span 3",
                padding: "2rem",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "1.5rem",
                background:
                  "linear-gradient(145deg, rgba(22, 25, 37, 0.8), rgba(99, 102, 241, 0.1))",
              }}
            >
              <h3
                style={{ fontSize: "1.125rem", color: "var(--text-primary)" }}
              >
                Scan in Progress
              </h3>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "1rem",
                  flexWrap: "wrap",
                  justifyContent: "center",
                }}
              >
                {[
                  { key: "Capturing", label: "Capturing Screenshots" },
                  { key: "Analyzing", label: "Analyzing with VLM" },
                  { key: "Fixing", label: "Applying AI Fixes" },
                  { key: "PR", label: "Generating PR" },
                ].map((item, idx) => {
                  const stageKeywords = ["captur", "analyz", "fix", "pr"];
                  const currentLower = (scanStage || "").toLowerCase();
                  const currentIdx = stageKeywords.findIndex((kw) => currentLower.includes(kw));
                  const isActive = currentIdx === idx;
                  const isPast = currentIdx > idx;

                  return (
                    <div
                      key={item.key}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "1rem",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.5rem",
                          color: isActive
                            ? "var(--accent-primary)"
                            : isPast
                              ? "var(--success)"
                              : "var(--text-muted)",
                          transition: "all 0.3s ease",
                        }}
                      >
                        {isPast ? (
                          <CheckCircle
                            size={20}
                            className="animate-fade-in"
                          />
                        ) : isActive ? (
                          <Activity className="animate-spin" size={20} />
                        ) : (
                          <div
                            style={{
                              width: "20px",
                              height: "20px",
                              borderRadius: "50%",
                              border: "2px solid currentColor",
                            }}
                          ></div>
                        )}
                        <span
                          style={{
                            fontWeight: isActive ? 600 : 400,
                            fontSize: "0.9375rem",
                          }}
                        >
                          {item.label}
                        </span>
                      </div>
                      {idx < 3 && (
                        <div
                          style={{
                            width: "40px",
                            height: "2px",
                            background: isPast
                              ? "var(--success)"
                              : "var(--border-glass)",
                            transition: "all 0.3s ease",
                          }}
                        ></div>
                      )}
                    </div>
                  );
                })}
              </div>
              <p
                style={{
                  color: "var(--text-secondary)",
                  fontSize: "0.875rem",
                  marginTop: "0.5rem",
                }}
                className="animate-pulse"
              >
                {scanStage}
              </p>
            </div>
          )}

          {/* Left Column: Recent Runs */}
          <div
            className="glass-panel card animate-fade-in delay-100"
            style={{ gridColumn: "span 1" }}
          >
            <h2
              className="card-title"
              style={{
                marginBottom: "1.5rem",
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              <Activity size={20} className="text-accent" />
              Recent Scans
            </h2>

            {loading ? (
              <div
                style={{
                  padding: "2rem",
                  textAlign: "center",
                  color: "var(--text-muted)",
                }}
              >
                Loading runs...
              </div>
            ) : runs.length === 0 ? (
              <div
                style={{
                  padding: "2rem",
                  textAlign: "center",
                  color: "var(--text-muted)",
                }}
              >
                No scans run yet.
              </div>
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "1rem",
                }}
              >
                {runs.map((run) => (
                  <div
                    key={run.run_id}
                    className="glass-panel"
                    style={{
                      padding: "1rem",
                      cursor: "pointer",
                      borderColor:
                        selectedRun === run.run_id
                          ? "var(--accent-primary)"
                          : "var(--border-glass)",
                      transition: "all 0.2s",
                    }}
                    onClick={() => viewRunDetails(run.run_id)}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.5rem",
                        }}
                      >
                        <span
                          className={`status-dot status-${run.status}`}
                        ></span>
                        <span style={{ fontWeight: 500, fontSize: "0.875rem" }}>
                          {new Date(run.started_at).toLocaleString()}
                        </span>
                      </div>
                      <ChevronRight size={16} color="var(--text-muted)" />
                    </div>
                    <div
                      className="card-meta"
                      style={{
                        marginTop: "0.75rem",
                        justifyContent: "space-between",
                      }}
                    >
                      <span
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.25rem",
                        }}
                      >
                        <Bug size={14} />
                        {run.total_bugs} bugs
                      </span>
                      <span style={{ textTransform: "capitalize" }}>
                        {run.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right Column: Run Details */}
          <div
            className="glass-panel card animate-fade-in delay-200"
            style={{ gridColumn: "span 2", minHeight: "500px" }}
          >
            {!selectedRun ? (
              <div
                style={{
                  height: "100%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "var(--text-muted)",
                }}
              >
                Select a scan from the left to view details
              </div>
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "1rem",
                  height: "100%",
                }}
              >
                {/* Collapsible Website Preview (Toggleable to save CPU/RAM) */}
                <div
                  style={{
                    width: "100%",
                    borderRadius: "10px",
                    overflow: "hidden",
                    border: "1px solid var(--border-glass)",
                    background: "rgba(255,255,255,0.02)",
                  }}
                >
                  <div
                    style={{
                      padding: "0.75rem 1rem",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      background: "rgba(255,255,255,0.03)",
                      borderBottom: showPreview ? "1px solid var(--border-glass)" : "none",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                      <Globe size={16} color="var(--accent-primary)" />
                      <span>Live Site Preview: <strong style={{ color: "var(--text-primary)" }}>{runs.find((r) => r.run_id === selectedRun)?.url || "Target Site"}</strong></span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <button
                        type="button"
                        onClick={() => {
                          setPreviewKey(Date.now());
                          setDownloadSuccessMsg("🔄 Refreshed live preview bypassing browser cache.");
                          setTimeout(() => setDownloadSuccessMsg(""), 4000);
                        }}
                        title="Force reload the preview site bypassing browser cache"
                        style={{
                          padding: "0.35rem 0.75rem",
                          fontSize: "0.75rem",
                          borderRadius: "6px",
                          border: "1px solid var(--border-glass)",
                          background: "rgba(255, 255, 255, 0.08)",
                          color: "var(--text-secondary)",
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.35rem",
                        }}
                      >
                        <RotateCcw size={13} />
                        Hard Reload Preview
                      </button>
                      <button
                        type="button"
                        onClick={() => setShowPreview(!showPreview)}
                        style={{
                          padding: "0.35rem 0.75rem",
                          fontSize: "0.75rem",
                          borderRadius: "6px",
                          border: "1px solid var(--border-glass)",
                          background: showPreview ? "rgba(239, 68, 68, 0.15)" : "rgba(99, 102, 241, 0.15)",
                          color: showPreview ? "#fca5a5" : "#a5b4fc",
                          cursor: "pointer",
                          fontWeight: 500,
                        }}
                      >
                        {showPreview ? "Hide Preview" : "Load Live Preview"}
                      </button>
                    </div>
                  </div>

                  {showPreview && (
                    <div style={{ width: "100%", height: "350px" }}>
                      {runs.find((r) => r.run_id === selectedRun)?.url ? (
                        <iframe
                          key={previewKey}
                          src={
                            runs.find((r) => r.run_id === selectedRun)?.url
                              ? `${runs.find((r) => r.run_id === selectedRun)?.url}${
                                  runs.find((r) => r.run_id === selectedRun)?.url.includes("?") ? "&" : "?"
                                }_cb=${previewKey}`
                              : ""
                          }
                          style={{
                            width: "100%",
                            height: "100%",
                            border: "none",
                            background: "#fff",
                          }}
                          loading="lazy"
                          title="Target Website Preview"
                        />
                      ) : (
                        <div
                          style={{
                            height: "100%",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            color: "var(--text-muted)",
                          }}
                        >
                          No URL available for preview
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {!runDetails ? (
                  <div
                    style={{
                      flex: 1,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "var(--text-muted)",
                    }}
                  >
                    <Activity
                      className="animate-spin"
                      style={{ marginRight: "0.5rem" }}
                    />
                    Loading details...
                  </div>
                ) : (
                  <div>
                    <div
                      className="card-header"
                      style={{
                        borderBottom: "1px solid var(--border-glass)",
                        paddingBottom: "1rem",
                      }}
                    >
                      <div>
                        <h2
                          className="card-title"
                          style={{ fontSize: "1.5rem" }}
                        >
                          Scan Details
                        </h2>
                        <div className="card-meta">ID: {runDetails.run_id}</div>
                      </div>
                      <div style={{ display: "flex", gap: "1rem" }}>
                        <div
                          className="glass-panel"
                          style={{
                            padding: "0.5rem 1rem",
                            display: "flex",
                            alignItems: "center",
                            gap: "0.5rem",
                          }}
                        >
                          <Clock size={16} />
                          {runDetails.duration_seconds
                            ? `${runDetails.duration_seconds.toFixed(2)}s`
                            : "N/A"}
                        </div>
                        <div
                          className="glass-panel"
                          style={{
                            padding: "0.5rem 1rem",
                            display: "flex",
                            alignItems: "center",
                            gap: "0.5rem",
                          }}
                        >
                          <Bug size={16} />
                          {runDetails.total_bugs} Bugs Found
                        </div>
                        {(runDetails.status === "COMPLETED" || runDetails.status === "completed") && (
                          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
                            {runDetails.pr_url ? (
                              <>
                                <a
                                  href={runDetails.pr_url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="btn"
                                  style={{
                                    padding: "0.5rem 1rem",
                                    background: "#10b981",
                                    color: "#fff",
                                    fontWeight: "bold",
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: "0.5rem",
                                    borderRadius: "8px",
                                    textDecoration: "none",
                                  }}
                                  title="Open the pull request created by OmniSight on GitHub"
                                >
                                  <CheckCircle size={16} />
                                  View PR on GitHub ↗
                                </a>
                                <button
                                  className="btn"
                                  disabled={syncingPr}
                                  onClick={() => handleSyncPr(runDetails.run_id)}
                                  style={{
                                    padding: "0.5rem 1rem",
                                    background: "#2563eb",
                                    color: "#fff",
                                    fontWeight: "bold",
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: "0.5rem",
                                    borderRadius: "8px",
                                    border: "none",
                                    cursor: "pointer",
                                    boxShadow: "0 2px 8px rgba(37, 99, 235, 0.3)",
                                  }}
                                  title="Check if the PR was merged on GitHub and immediately sync changes to the live site"
                                >
                                  {syncingPr ? (
                                    <Activity className="animate-spin" size={16} />
                                  ) : (
                                    <RotateCcw size={16} />
                                  )}
                                  {syncingPr ? "Syncing PR..." : "🔄 Sync Merged PR to Site"}
                                </button>
                              </>
                            ) : (
                              <button
                                className="btn-github-pr"
                                disabled={creatingPr}
                                onClick={() => handleCreatePr(runDetails.run_id)}
                                title={
                                  githubStatus.configured
                                    ? "Autonomously push fixes and open Pull Request on GitHub"
                                    : "Connect your GitHub account to enable 1-click PR"
                                }
                              >
                                {creatingPr ? (
                                  <Activity className="animate-spin" size={16} />
                                ) : (
                                  <GitPullRequest size={16} />
                                )}
                                {creatingPr ? "Pushing PR to GitHub..." : "🚀 Push Fixes to GitHub (Open PR)"}
                              </button>
                            )}

                            <a
                              href={`${API_BASE}/scans/${runDetails.run_id}/fixed_code.txt`}
                              download="fixed_code.txt"
                              className="btn"
                              style={{
                                padding: "0.5rem 1rem",
                                background: "#059669",
                                color: "#fff",
                                fontWeight: "bold",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.5rem",
                                cursor: "pointer",
                                borderRadius: "8px",
                                border: "none",
                                textDecoration: "none",
                              }}
                              title="Download fixed code directly as a Windows Notepad (.txt) file"
                              onClick={() => {
                                setDownloadSuccessMsg("✅ Downloaded 'fixed_code.txt'! Double-click in Downloads to open in Windows Notepad.");
                                setTimeout(() => setDownloadSuccessMsg(""), 6000);
                              }}
                            >
                              <FileText size={16} />
                              Download Notepad File (.txt)
                            </a>
                            <button
                              className="btn"
                              style={{
                                padding: "0.5rem 1rem",
                                background: "#0284c7",
                                color: "#fff",
                                fontWeight: "bold",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.5rem",
                                cursor: "pointer",
                                borderRadius: "8px",
                                border: "none",
                              }}
                              title="Instantly open the fixed code directly inside Windows Notepad on your PC"
                              onClick={() => handleOpenNotepad(runDetails.run_id)}
                            >
                              <ExternalLink size={16} />
                              Open in Notepad
                            </button>

                            <a
                              href={`${API_BASE}/scans/${runDetails.run_id}/omnisight_scan_fixes.zip`}
                              download="omnisight_scan_fixes.zip"
                              className="btn btn-primary"
                              style={{
                                padding: "0.5rem 1rem",
                                background: "var(--accent-primary)",
                                color: "#fff",
                                fontWeight: "bold",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.5rem",
                                cursor: "pointer",
                                borderRadius: "8px",
                                textDecoration: "none",
                              }}
                              title="Download complete ZIP containing fixed_code.txt, styles.css, and index.html"
                              onClick={() => {
                                setDownloadSuccessMsg("✅ Downloaded 'omnisight_scan_fixes.zip'! You can open it in File Explorer. Also saved to your Downloads folder.");
                                setTimeout(() => setDownloadSuccessMsg(""), 6000);
                              }}
                            >
                              <Download size={16} />
                              Download ZIP (.zip)
                            </a>
                            <button
                              className="btn"
                              style={{
                                padding: "0.5rem 1rem",
                                background: "#334155",
                                color: "#fff",
                                fontWeight: "bold",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.5rem",
                                cursor: "pointer",
                                borderRadius: "8px",
                                border: "none",
                              }}
                              title="View or copy Notepad code directly on screen"
                              onClick={() => setShowNotepadCode(!showNotepadCode)}
                            >
                              <Eye size={16} />
                              {showNotepadCode ? "Hide Notepad View" : "View Code on Screen"}
                            </button>
                          </div>
                        )}
                      </div>
                    </div>

                    {downloadSuccessMsg && (
                      <div
                        style={{
                          marginTop: "1rem",
                          padding: "0.85rem 1.25rem",
                          background: "rgba(16, 185, 129, 0.15)",
                          border: "1px solid #10b981",
                          borderRadius: "8px",
                          color: "#6ee7b7",
                          fontSize: "0.9rem",
                          fontWeight: "500",
                        }}
                      >
                        {downloadSuccessMsg}
                      </div>
                    )}

                    {showNotepadCode && (
                      <div
                        className="glass-panel"
                        style={{
                          marginTop: "1.5rem",
                          padding: "1.5rem",
                          background: "#020617",
                          border: "1px solid #38bdf8",
                          borderRadius: "10px",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            marginBottom: "1rem",
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <FileText size={20} color="#38bdf8" />
                            <h4 style={{ margin: 0, color: "#f8fafc", fontSize: "1.05rem" }}>
                              Notepad Code Viewer — fixed_code.txt
                            </h4>
                          </div>
                          <div style={{ display: "flex", gap: "0.5rem" }}>
                            <button
                              className="btn"
                              style={{
                                padding: "0.4rem 0.8rem",
                                background: copySuccess ? "#10b981" : "#1e293b",
                                color: "#fff",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.4rem",
                                cursor: "pointer",
                                borderRadius: "6px",
                                border: "1px solid #475569",
                                fontSize: "0.85rem",
                              }}
                              onClick={handleCopyNotepadCode}
                            >
                              {copySuccess ? <Check size={14} /> : <Copy size={14} />}
                              {copySuccess ? "Copied!" : "Copy Notepad Code"}
                            </button>
                            <a
                              href={`${API_BASE}/scans/${runDetails.run_id}/fixed_code.txt`}
                              download="fixed_code.txt"
                              className="btn"
                              style={{
                                padding: "0.4rem 0.8rem",
                                background: "#059669",
                                color: "#fff",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.4rem",
                                cursor: "pointer",
                                borderRadius: "6px",
                                border: "none",
                                fontSize: "0.85rem",
                                textDecoration: "none",
                              }}
                              onClick={() => {
                                setDownloadSuccessMsg("✅ Downloaded 'fixed_code.txt'! Double-click in Downloads to open in Windows Notepad.");
                                setTimeout(() => setDownloadSuccessMsg(""), 6000);
                              }}
                            >
                              <Download size={14} />
                              Save as .txt
                            </a>
                          </div>
                        </div>
                        <textarea
                          readOnly
                          value={notepadContent || "Loading fixed code in Notepad format..."}
                          rows={14}
                          style={{
                            width: "100%",
                            background: "#090d16",
                            color: "#e2e8f0",
                            border: "1px solid #1e293b",
                            borderRadius: "6px",
                            padding: "1rem",
                            fontFamily: "Consolas, 'Courier New', monospace",
                            fontSize: "0.85rem",
                            lineHeight: "1.5",
                            resize: "vertical",
                            boxSizing: "border-box",
                          }}
                        />
                      </div>
                    )}

                    <div style={{ marginTop: "2rem" }}>
                      <h3 style={{ marginBottom: "1rem" }}>Detected Issues</h3>
                      {runDetails.status === "RUNNING" || runDetails.status === "running" ? (
                        <div
                          className="glass-panel"
                          style={{
                            padding: "2rem",
                            textAlign: "center",
                            color: "var(--text-muted)",
                          }}
                        >
                          <Activity
                            className="animate-spin"
                            size={48}
                            style={{ margin: "0 auto 1rem", color: "var(--accent-primary)" }}
                          />
                          <p>Analyzing UI for bugs...</p>
                        </div>
                      ) : runDetails.bugs.length === 0 ? (
                        <div
                          className="glass-panel"
                          style={{
                            padding: "2rem",
                            textAlign: "center",
                            color: "var(--success)",
                          }}
                        >
                          <CheckCircle
                            size={48}
                            style={{ margin: "0 auto 1rem" }}
                          />
                          <p>No UI bugs detected in this scan!</p>
                        </div>
                      ) : (
                        <div className="grid grid-cols-1">
                          {runDetails.bugs.map((bug, index) => (
                            <div
                              key={bug.id}
                              className="glass-panel animate-fade-in"
                              style={{
                                padding: "1.5rem",
                                animationDelay: `${index * 100}ms`,
                              }}
                            >
                              <div
                                style={{
                                  display: "flex",
                                  justifyContent: "space-between",
                                  alignItems: "flex-start",
                                  marginBottom: "1rem",
                                }}
                              >
                                <h4
                                  style={{
                                    fontSize: "1.125rem",
                                    color: "var(--text-primary)",
                                    display: "flex",
                                    alignItems: "center",
                                    flexWrap: "wrap",
                                    gap: "0.5rem",
                                  }}
                                >
                                  {bug.title}
                                  {bug.verification_status ===
                                    "verified_fixed" && (
                                    <span
                                      className="badge"
                                      style={{
                                        background: "rgba(16, 185, 129, 0.15)",
                                        color: "#6ee7b7",
                                        border:
                                          "1px solid rgba(16, 185, 129, 0.3)",
                                        display: "inline-flex",
                                        alignItems: "center",
                                        gap: "4px",
                                      }}
                                    >
                                      <CheckCircle size={12} /> Verified Fixed
                                    </span>
                                  )}
                                  {bug.verification_status ===
                                    "still_broken" && (
                                    <span
                                      className="badge"
                                      style={{
                                        background: "rgba(239, 68, 68, 0.15)",
                                        color: "#fca5a5",
                                        border:
                                          "1px solid rgba(239, 68, 68, 0.3)",
                                        display: "inline-flex",
                                        alignItems: "center",
                                        gap: "4px",
                                      }}
                                    >
                                      <XCircle size={12} /> Still Broken
                                    </span>
                                  )}
                                </h4>
                                <span className={`badge badge-${bug.severity}`}>
                                  {bug.severity}
                                </span>
                              </div>

                              <p
                                style={{
                                  color: "var(--text-secondary)",
                                  marginBottom: "1rem",
                                }}
                              >
                                {bug.description}
                              </p>

                              <div
                                style={{
                                  display: "grid",
                                  gridTemplateColumns: "1fr 1fr",
                                  gap: "1rem",
                                  fontSize: "0.875rem",
                                }}
                              >
                                <div>
                                  <span
                                    style={{
                                      color: "var(--text-muted)",
                                      display: "block",
                                      marginBottom: "0.25rem",
                                    }}
                                  >
                                    Category
                                  </span>
                                  <span style={{ textTransform: "capitalize" }}>
                                    {bug.category}
                                  </span>
                                </div>
                                <div>
                                  <span
                                    style={{
                                      color: "var(--text-muted)",
                                      display: "block",
                                      marginBottom: "0.25rem",
                                    }}
                                  >
                                    Viewport
                                  </span>
                                  <span style={{ textTransform: "capitalize" }}>
                                    {bug.viewport}
                                  </span>
                                </div>
                                <div style={{ gridColumn: "span 2" }}>
                                  <span
                                    style={{
                                      color: "var(--text-muted)",
                                      display: "block",
                                      marginBottom: "0.25rem",
                                    }}
                                  >
                                    Affected Element
                                  </span>
                                  <code
                                    style={{
                                      background: "rgba(255,255,255,0.05)",
                                      padding: "0.25rem 0.5rem",
                                      borderRadius: "4px",
                                    }}
                                  >
                                    {bug.element_selector || "N/A"}
                                  </code>
                                </div>
                                {bug.suggested_fix && (
                                  <div
                                    style={{
                                      gridColumn: "span 2",
                                      marginTop: "0.5rem",
                                    }}
                                  >
                                    <span
                                      style={{
                                        color: "var(--accent-primary)",
                                        display: "block",
                                        marginBottom: "0.5rem",
                                        fontWeight: 500,
                                      }}
                                    >
                                      AI Suggested Fix
                                    </span>
                                    <pre>{bug.suggested_fix}</pre>

                                    <div
                                      style={{
                                        marginTop: "1rem",
                                        display: "flex",
                                        gap: "0.75rem",
                                        alignItems: "center",
                                      }}
                                    >
                                      {bugStatuses[bug.id] ? (
                                        <div
                                          style={{
                                            color:
                                              bugStatuses[bug.id].status ===
                                              "approved"
                                                ? "var(--success)"
                                                : "var(--error)",
                                            display: "flex",
                                            alignItems: "center",
                                            gap: "0.5rem",
                                          }}
                                        >
                                          {bugStatuses[bug.id].status ===
                                          "approved" ? (
                                            <CheckCircle size={16} />
                                          ) : (
                                            <XCircle size={16} />
                                          )}
                                          <span
                                            style={{
                                              textTransform: "capitalize",
                                            }}
                                          >
                                            Fix {bugStatuses[bug.id].status}
                                          </span>
                                          {bugStatuses[bug.id].prUrl && (
                                            <a
                                              href={bugStatuses[bug.id].prUrl}
                                              target="_blank"
                                              rel="noreferrer"
                                              style={{
                                                marginLeft: "1rem",
                                                color: "var(--accent-primary)",
                                                textDecoration: "underline",
                                              }}
                                            >
                                              View Pull Request
                                            </a>
                                          )}
                                        </div>
                                      ) : (
                                        <>
                                          <button
                                            className="btn btn-primary"
                                            onClick={() =>
                                              handleBugAction(bug.id, "approve")
                                            }
                                            disabled={actioningBug === bug.id}
                                            style={{
                                              padding: "0.5rem 1rem",
                                              fontSize: "0.875rem",
                                            }}
                                          >
                                            {actioningBug === bug.id
                                              ? "Processing..."
                                              : "Approve Fix (Create PR)"}
                                          </button>
                                          <button
                                            className="btn"
                                            onClick={() =>
                                              handleBugAction(bug.id, "reject")
                                            }
                                            disabled={actioningBug === bug.id}
                                            style={{
                                              padding: "0.5rem 1rem",
                                              fontSize: "0.875rem",
                                              background:
                                                "rgba(255,255,255,0.05)",
                                            }}
                                          >
                                            Reject
                                          </button>
                                        </>
                                      )}
                                    </div>
                                  </div>
                                )}

                                {bug.verification_status && (
                                  <div
                                    className="card"
                                    style={{
                                      gridColumn: "span 2",
                                      marginTop: "1.5rem",
                                      background: "rgba(0,0,0,0.4)",
                                      borderRadius: "12px",
                                    }}
                                  >
                                    <h5
                                      style={{
                                        marginBottom: "1.5rem",
                                        color: "var(--text-primary)",
                                        display: "flex",
                                        alignItems: "center",
                                        gap: "0.75rem",
                                        fontSize: "1.1rem",
                                      }}
                                    >
                                      <Activity
                                        size={20}
                                        className="text-accent"
                                      />
                                      Visual Verification
                                    </h5>
                                    <div
                                      style={{
                                        display: "grid",
                                        gridTemplateColumns: "1fr 1fr",
                                        gap: "2rem",
                                      }}
                                    >
                                      <div style={{ position: "relative" }}>
                                        <span
                                          style={{
                                            position: "absolute",
                                            top: "10px",
                                            left: "10px",
                                            zIndex: 10,
                                            background: "rgba(0,0,0,0.7)",
                                            padding: "4px 12px",
                                            borderRadius: "20px",
                                            color: "white",
                                            fontSize: "0.75rem",
                                            backdropFilter: "blur(4px)",
                                            border:
                                              "1px solid rgba(255,255,255,0.1)",
                                          }}
                                        >
                                          Original
                                        </span>
                                        {bug.screenshot_path ? (
                                          <div
                                            className="card"
                                            style={{
                                              padding: 0,
                                              borderRadius: "12px",
                                              overflow: "hidden",
                                              background: "#000",
                                              aspectRatio: "16/9",
                                              display: "flex",
                                              alignItems: "center",
                                              justifyContent: "center",
                                            }}
                                          >
                                            <img
                                              src={
                                                bug.screenshot_path.startsWith(
                                                  "http",
                                                )
                                                  ? bug.screenshot_path
                                                  : `http://localhost:8000/${bug.screenshot_path}`
                                              }
                                              alt="Before"
                                              style={{
                                                width: "100%",
                                                height: "100%",
                                                objectFit: "cover",
                                                opacity: 0.8,
                                                transition:
                                                  "opacity 0.3s, transform 0.5s",
                                              }}
                                              onMouseOver={(e) => {
                                                e.currentTarget.style.opacity = 1;
                                                e.currentTarget.style.transform =
                                                  "scale(1.05)";
                                              }}
                                              onMouseOut={(e) => {
                                                e.currentTarget.style.opacity = 0.8;
                                                e.currentTarget.style.transform =
                                                  "scale(1)";
                                              }}
                                              onError={(e) => {
                                                e.target.style.display = "none";
                                                e.target.nextSibling.style.display =
                                                  "flex";
                                              }}
                                            />
                                            <div
                                              style={{
                                                display: "none",
                                                color: "var(--text-muted)",
                                                fontSize: "0.875rem",
                                                textAlign: "center",
                                                padding: "1rem",
                                              }}
                                            >
                                              Image path:
                                              <br />
                                              {bug.screenshot_path
                                                .split(/[\\/]/)
                                                .pop()}
                                            </div>
                                          </div>
                                        ) : (
                                          <div
                                            style={{
                                              background:
                                                "rgba(255,255,255,0.02)",
                                              padding: "2rem",
                                              textAlign: "center",
                                              borderRadius: "12px",
                                            }}
                                          >
                                            N/A
                                          </div>
                                        )}
                                      </div>
                                      <div style={{ position: "relative" }}>
                                        <span
                                          style={{
                                            position: "absolute",
                                            top: "10px",
                                            left: "10px",
                                            zIndex: 10,
                                            background:
                                              "linear-gradient(135deg, var(--success), #047857)",
                                            padding: "4px 12px",
                                            borderRadius: "20px",
                                            color: "white",
                                            fontSize: "0.75rem",
                                            backdropFilter: "blur(4px)",
                                            border:
                                              "1px solid rgba(255,255,255,0.2)",
                                            boxShadow:
                                              "0 4px 10px rgba(16, 185, 129, 0.4)",
                                          }}
                                        >
                                          Fixed
                                        </span>
                                        {bug.verification_screenshot_path ? (
                                          <div
                                            className="card"
                                            style={{
                                              padding: 0,
                                              borderRadius: "12px",
                                              overflow: "hidden",
                                              background: "#000",
                                              aspectRatio: "16/9",
                                              display: "flex",
                                              alignItems: "center",
                                              justifyContent: "center",
                                            }}
                                          >
                                            <img
                                              src={
                                                bug.verification_screenshot_path.startsWith(
                                                  "http",
                                                )
                                                  ? bug.verification_screenshot_path
                                                  : `http://localhost:8000/${bug.verification_screenshot_path}`
                                              }
                                              alt="After"
                                              style={{
                                                width: "100%",
                                                height: "100%",
                                                objectFit: "cover",
                                                opacity: 0.8,
                                                transition:
                                                  "opacity 0.3s, transform 0.5s",
                                              }}
                                              onMouseOver={(e) => {
                                                e.currentTarget.style.opacity = 1;
                                                e.currentTarget.style.transform =
                                                  "scale(1.05)";
                                              }}
                                              onMouseOut={(e) => {
                                                e.currentTarget.style.opacity = 0.8;
                                                e.currentTarget.style.transform =
                                                  "scale(1)";
                                              }}
                                              onError={(e) => {
                                                e.target.style.display = "none";
                                                e.target.nextSibling.style.display =
                                                  "flex";
                                              }}
                                            />
                                            <div
                                              style={{
                                                display: "none",
                                                color: "var(--text-muted)",
                                                fontSize: "0.875rem",
                                                textAlign: "center",
                                                padding: "1rem",
                                              }}
                                            >
                                              Image path:
                                              <br />
                                              {bug.verification_screenshot_path
                                                .split(/[\\/]/)
                                                .pop()}
                                            </div>
                                          </div>
                                        ) : (
                                          <div
                                            style={{
                                              background:
                                                "rgba(255,255,255,0.02)",
                                              padding: "2rem",
                                              textAlign: "center",
                                              borderRadius: "12px",
                                            }}
                                          >
                                            N/A
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </main>
        )}
      </div>

      {/* GitHub Authentication Modal */}
      {showGithubModal && (
        <div className="modal-backdrop" onClick={() => setShowGithubModal(false)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                <GitPullRequest size={22} color="var(--accent-primary)" />
                <h3 style={{ margin: 0, fontSize: "1.25rem", color: "#f8fafc" }}>Connect GitHub Account</h3>
              </div>
              <button
                onClick={() => setShowGithubModal(false)}
                style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", padding: "0.25rem" }}
              >
                <X size={20} />
              </button>
            </div>

            <p style={{ color: "#94a3b8", fontSize: "0.875rem", lineHeight: "1.5", marginBottom: "1.25rem" }}>
              Authenticate OmniSight with your GitHub Personal Access Token to enable <strong>1-click autonomous Pull Requests</strong> directly to your repository.
            </p>

            <form onSubmit={handleConnectGithub}>
              <div style={{ marginBottom: "1rem" }}>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: "600", color: "#cbd5e1", marginBottom: "0.4rem" }}>
                  GitHub Personal Access Token (Classic) <span style={{ color: "#ef4444" }}>*</span>
                </label>
                <input
                  type="password"
                  value={githubTokenInput}
                  onChange={(e) => setGithubTokenInput(e.target.value)}
                  placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                  style={{
                    width: "100%",
                    padding: "0.75rem",
                    background: "#090d16",
                    border: "1px solid #334155",
                    borderRadius: "8px",
                    color: "#f8fafc",
                    fontSize: "0.9rem",
                    boxSizing: "border-box",
                  }}
                />
                <span style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.3rem", display: "block" }}>
                  Requires <code style={{ color: "#38bdf8" }}>repo</code> scope. Generate on GitHub → Settings → Developer settings → Personal access tokens.
                </span>
              </div>

              <div style={{ marginBottom: "1.5rem" }}>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: "600", color: "#cbd5e1", marginBottom: "0.4rem" }}>
                  Default Target Repository (Optional)
                </label>
                <input
                  type="text"
                  value={githubRepoInput}
                  onChange={(e) => setGithubRepoInput(e.target.value)}
                  placeholder="e.g. samuelwinstonparker6-debug/Portfolio"
                  style={{
                    width: "100%",
                    padding: "0.75rem",
                    background: "#090d16",
                    border: "1px solid #334155",
                    borderRadius: "8px",
                    color: "#f8fafc",
                    fontSize: "0.9rem",
                    boxSizing: "border-box",
                  }}
                />
                <span style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.3rem", display: "block" }}>
                  Leave empty to auto-detect from scanned URL.
                </span>
              </div>

              {githubError && (
                <div style={{ marginBottom: "1rem", padding: "0.75rem", background: "rgba(239, 68, 68, 0.15)", border: "1px solid #ef4444", borderRadius: "6px", color: "#fca5a5", fontSize: "0.85rem" }}>
                  {githubError}
                </div>
              )}

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <button
                  type="button"
                  onClick={() => setShowGithubModal(false)}
                  style={{
                    padding: "0.6rem 1.2rem",
                    background: "transparent",
                    border: "1px solid #334155",
                    color: "#94a3b8",
                    borderRadius: "8px",
                    cursor: "pointer",
                    fontWeight: "600",
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={connectingGithub}
                  style={{
                    padding: "0.6rem 1.4rem",
                    background: "var(--accent-primary)",
                    border: "none",
                    color: "#ffffff",
                    borderRadius: "8px",
                    cursor: "pointer",
                    fontWeight: "700",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.5rem",
                  }}
                >
                  {connectingGithub ? <Activity size={16} className="animate-spin" /> : <Key size={16} />}
                  {connectingGithub ? "Verifying..." : "Save & Authenticate"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
  /* close the conditional main tag opened above when not on design view */
}


export default App;
