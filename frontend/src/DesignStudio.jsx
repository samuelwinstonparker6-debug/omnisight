import { useState, useRef, useEffect } from "react";
import {
  Sparkles,
  GitPullRequest,
  Copy,
  Check,
  ExternalLink,
  Loader2,
  Send,
  Trash2,
  ChevronDown,
  ChevronUp,
  Wand2,
  RotateCcw,
  Bug,
  Eye,
  Zap,
  Code2,
  Globe,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Info,
  ArrowRight,
} from "lucide-react";

const API_BASE =
  typeof window !== "undefined" && window.location.port === "5173"
    ? "/api/v1"
    : "http://localhost:8000/api/v1";

// ─────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────
const SUGGESTIONS = [
  "Make the hero section a full-width gradient with cyan and indigo accents",
  "Redesign the sidebar with glassmorphism and a dark slate background",
  "Add smooth hover animations to all buttons with a glowing box-shadow",
  "Change the color scheme to a warm amber and rose dark palette",
  "Make all cards have a frosted-glass effect with subtle border glow",
  "Increase heading font sizes and use a bold, modern typeface",
  "Add a pulsing neon outline to the primary call-to-action buttons",
  "Fix any UI bugs and also make the layout full-bleed with more breathing room",
  "Detect and fix all contrast and visibility issues on the page",
  "Add a sticky navigation bar with a glassmorphism blur effect",
];

const INTENT_META = {
  design: {
    label: "🎨 Design Change",
    color: "#6366f1",
    bg: "rgba(99,102,241,0.12)",
    border: "rgba(99,102,241,0.35)",
    desc: "Gemini will generate CSS/UI changes from your prompt",
  },
  bugfix: {
    label: "🐛 Bug Detection & Fix",
    color: "#f59e0b",
    bg: "rgba(245,158,11,0.12)",
    border: "rgba(245,158,11,0.35)",
    desc: "OmniSight will scan the page for bugs and auto-fix them",
  },
  both: {
    label: "⚡ Design + Bug Fix",
    color: "#10b981",
    bg: "rgba(16,185,129,0.12)",
    border: "rgba(16,185,129,0.35)",
    desc: "Runs bug detection AND applies your design changes — all in one PR",
  },
};

const PIPELINE_STAGES = [
  { id: "interpret", label: "Interpreting", icon: <Zap size={14} /> },
  { id: "bugdetect", label: "Scanning Bugs", icon: <Bug size={14} /> },
  { id: "generate", label: "Generating CSS", icon: <Code2 size={14} /> },
  { id: "pr", label: "Creating PR", icon: <GitPullRequest size={14} /> },
];

// ─────────────────────────────────────────────────────────
// Keyword-based fast intent preview (mirrors backend logic)
// ─────────────────────────────────────────────────────────
const BUG_KW = [
  "fix bug", "detect bug", "find bug", "ui bug", "broken", "glitch",
  "contrast issue", "visibility", "overlap", "clipped", "overflow",
  "misalign", "regression", "wcag", "low contrast", "blurred", "washed out",
  "fix the issue", "find issues", "detect issues", "fix issues", "repair",
];
const DESIGN_KW = [
  "redesign", "change the", "make the", "add a", "remove the", "update the",
  "style", "color", "layout", "font", "animation", "glassmorphism", "dark mode",
  "theme", "gradient", "hero", "nav", "sidebar", "card", "button", "padding",
  "spacing", "responsive", "fullwidth", "background", "border", "shadow",
  "modern", "aesthetic",
];

function detectIntent(prompt) {
  const lower = prompt.toLowerCase();
  const hasBug = BUG_KW.some((k) => lower.includes(k));
  const hasDesign = DESIGN_KW.some((k) => lower.includes(k));
  if (hasBug && hasDesign) return "both";
  if (hasBug) return "bugfix";
  return "design";
}

// ─────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────
function StatusBanner({ msg, onClose }) {
  if (!msg) return null;
  const colors = {
    success: { bg: "rgba(16,185,129,0.12)", border: "rgba(16,185,129,0.3)", text: "#34d399", icon: "✅" },
    error: { bg: "rgba(239,68,68,0.12)", border: "rgba(239,68,68,0.3)", text: "#f87171", icon: "❌" },
    info: { bg: "rgba(59,130,246,0.12)", border: "rgba(59,130,246,0.3)", text: "#60a5fa", icon: "ℹ️" },
    warning: { bg: "rgba(245,158,11,0.12)", border: "rgba(245,158,11,0.3)", text: "#fbbf24", icon: "⚠️" },
  };
  const c = colors[msg.type] || colors.info;
  return (
    <div style={{
      padding: "0.8rem 1rem", borderRadius: "8px", fontSize: "0.875rem",
      display: "flex", alignItems: "center", gap: "0.6rem",
      background: c.bg, border: `1px solid ${c.border}`, color: c.text,
    }}>
      <span style={{ flex: 1 }}>{c.icon} {msg.text}</span>
      {msg.link && (
        <a href={msg.link} target="_blank" rel="noopener noreferrer"
          style={{ display: "flex", alignItems: "center", gap: "0.3rem", color: "inherit", fontWeight: 600 }}>
          View PR <ExternalLink size={13} />
        </a>
      )}
      <button onClick={onClose}
        style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", opacity: 0.7 }}>
        ✕
      </button>
    </div>
  );
}

function PipelineProgress({ stage, subStatus, progressPercent }) {
  const currentIdx = PIPELINE_STAGES.findIndex((p) => p.id === stage);

  return (
    <div style={{
      position: "relative",
      background: "linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(22, 25, 37, 0.95))",
      borderRadius: "14px",
      border: "1px solid rgba(99, 102, 241, 0.35)",
      boxShadow: "0 12px 36px -4px rgba(0,0,0,0.5), 0 0 25px rgba(99,102,241,0.18)",
      overflow: "hidden",
      padding: "1.25rem 1.5rem",
      display: "flex",
      flexDirection: "column",
      gap: "1.1rem",
    }}>
      {/* Laser sweep animation line across the panel */}
      <div style={{
        position: "absolute",
        top: 0,
        bottom: 0,
        width: "30%",
        background: "linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.12), transparent)",
        pointerEvents: "none",
        animation: "laserSweep 3s infinite ease-in-out",
      }} />

      {/* Top glowing progress bar */}
      <div style={{
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        height: "3px",
        background: "rgba(255,255,255,0.06)",
      }}>
        <div style={{
          height: "100%",
          width: `${progressPercent || 20}%`,
          background: "linear-gradient(90deg, #6366f1, #38bdf8, #10b981)",
          boxShadow: "0 0 10px rgba(99,102,241,0.8)",
          transition: "width 0.6s cubic-bezier(0.4, 0, 0.2, 1)",
        }} />
      </div>

      {/* Stage Nodes Bar */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "0.5rem",
        position: "relative",
        zIndex: 1,
        flexWrap: "wrap",
      }}>
        {PIPELINE_STAGES.map((s, i) => {
          const isActive = s.id === stage;
          const isDone = i < currentIdx;

          return (
            <div key={s.id} style={{ display: "flex", alignItems: "center", flex: 1, minWidth: "130px" }}>
              {/* Step Card / Pill */}
              <div
                className={isActive ? "studio-active-node" : ""}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.6rem",
                  padding: "0.6rem 0.95rem",
                  borderRadius: "10px",
                  fontSize: "0.82rem",
                  fontWeight: isActive ? 600 : 500,
                  transition: "all 0.3s ease",
                  width: "100%",
                  background: isDone
                    ? "rgba(16, 185, 129, 0.1)"
                    : isActive
                    ? "linear-gradient(135deg, rgba(99, 102, 241, 0.25), rgba(59, 130, 246, 0.15))"
                    : "rgba(255, 255, 255, 0.03)",
                  border: isDone
                    ? "1px solid rgba(16, 185, 129, 0.35)"
                    : isActive
                    ? "1px solid rgba(99, 102, 241, 0.7)"
                    : "1px solid rgba(255, 255, 255, 0.06)",
                  color: isDone
                    ? "#34d399"
                    : isActive
                    ? "#ffffff"
                    : "var(--text-muted)",
                }}
              >
                {/* Icon with animated beacon/spinner */}
                <div style={{
                  width: "24px",
                  height: "24px",
                  borderRadius: "6px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                  background: isDone
                    ? "rgba(16, 185, 129, 0.2)"
                    : isActive
                    ? "rgba(99, 102, 241, 0.35)"
                    : "rgba(255, 255, 255, 0.05)",
                  color: isDone ? "#10b981" : isActive ? "#818cf8" : "inherit",
                }}>
                  {isDone ? (
                    <CheckCircle2 size={16} color="#10b981" />
                  ) : isActive ? (
                    <Loader2 size={16} className="animate-spin" color="#a5b4fc" />
                  ) : (
                    <span style={{ fontSize: "0.72rem", fontWeight: 700, opacity: 0.6 }}>0{i + 1}</span>
                  )}
                </div>

                <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                  <span style={{
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}>
                    {s.label}
                  </span>
                  {isActive && (
                    <span style={{
                      fontSize: "0.68rem",
                      color: "#93c5fd",
                      fontWeight: 400,
                      display: "flex",
                      alignItems: "center",
                      gap: "0.3rem",
                    }}>
                      <span style={{
                        width: "5px",
                        height: "5px",
                        borderRadius: "50%",
                        background: "#38bdf8",
                        display: "inline-block",
                        animation: "liveBeaconPing 1.4s infinite ease-out",
                      }} />
                      Active
                    </span>
                  )}
                </div>
              </div>

              {/* Connector line between steps */}
              {i < PIPELINE_STAGES.length - 1 && (
                <div style={{
                  width: "24px",
                  height: "2px",
                  margin: "0 0.35rem",
                  flexShrink: 0,
                  background: isDone
                    ? "#10b981"
                    : isActive
                    ? "linear-gradient(90deg, #6366f1, #38bdf8, #6366f1)"
                    : "rgba(255, 255, 255, 0.08)",
                  backgroundSize: "200% 100%",
                  animation: isActive ? "energyTrackFlow 1.6s linear infinite" : "none",
                  boxShadow: isActive ? "0 0 8px rgba(99,102,241,0.6)" : "none",
                }} />
              )}
            </div>
          );
        })}
      </div>

      {/* Live AI Engine Activity Ticker */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0.55rem 0.9rem",
        background: "rgba(0, 0, 0, 0.35)",
        borderRadius: "8px",
        border: "1px solid rgba(255, 255, 255, 0.06)",
        fontSize: "0.78rem",
        color: "var(--text-secondary)",
        position: "relative",
        zIndex: 1,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.65rem", minWidth: 0, flex: 1 }}>
          {/* Animated soundwave / neural equalizer bars */}
          <div style={{ display: "flex", alignItems: "center", gap: "2.5px", height: "14px", flexShrink: 0 }}>
            <span style={{ width: "3px", borderRadius: "1px", background: "#818cf8", animation: "soundWaveBar 1.2s infinite ease-in-out" }} />
            <span style={{ width: "3px", borderRadius: "1px", background: "#38bdf8", animation: "soundWaveBar 1.2s infinite ease-in-out 0.25s" }} />
            <span style={{ width: "3px", borderRadius: "1px", background: "#34d399", animation: "soundWaveBar 1.2s infinite ease-in-out 0.5s" }} />
          </div>
          <span style={{
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            color: "#e2e8f0",
            fontFamily: "monospace",
          }}>
            {subStatus || "Studio engine active..."}
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexShrink: 0, paddingLeft: "0.5rem" }}>
          <span style={{
            padding: "0.15rem 0.5rem",
            borderRadius: "4px",
            background: "rgba(99, 102, 241, 0.2)",
            color: "#a5b4fc",
            fontWeight: 600,
            fontSize: "0.7rem",
            fontFamily: "monospace",
          }}>
            {Math.round(progressPercent || 0)}%
          </span>
        </div>
      </div>
    </div>
  );
}

function BugCard({ bug, idx }) {
  const sev = (bug.severity || "low").toLowerCase();
  const sevColor = sev === "critical" ? "#ef4444" : sev === "high" ? "#f97316" : sev === "medium" ? "#f59e0b" : "#6366f1";
  return (
    <div style={{
      padding: "0.75rem 1rem", borderRadius: "8px",
      border: `1px solid ${sevColor}33`, background: `${sevColor}0d`,
      fontSize: "0.82rem",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
        <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{bug.title || `Bug #${idx + 1}`}</span>
        <span style={{
          padding: "0.15rem 0.5rem", borderRadius: "20px", fontSize: "0.7rem",
          background: `${sevColor}22`, color: sevColor, fontWeight: 600, whiteSpace: "nowrap"
        }}>{sev.toUpperCase()}</span>
      </div>
      {bug.description && (
        <p style={{ color: "var(--text-secondary)", marginTop: "0.3rem", lineHeight: 1.5 }}>{bug.description}</p>
      )}
      {bug.element_selector && (
        <code style={{ fontSize: "0.7rem", color: "#a5f3fc", background: "rgba(0,0,0,0.3)", padding: "0.1rem 0.4rem", borderRadius: "4px" }}>
          {bug.element_selector}
        </code>
      )}
    </div>
  );
}

function ActionPlanCard({ plan }) {
  const [expanded, setExpanded] = useState(false);
  if (!plan || !plan.actions?.length) return null;
  return (
    <div className="glass-panel" style={{ overflow: "hidden" }}>
      <button onClick={() => setExpanded((v) => !v)} style={{
        width: "100%", padding: "0.875rem 1.25rem",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: "none", border: "none", cursor: "pointer",
        borderBottom: expanded ? "1px solid var(--border-glass)" : "none",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
          <Code2 size={15} color="var(--accent-primary)" />
          <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>
            Action Plan <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>({plan.actions.length} actions)</span>
          </span>
        </div>
        {expanded ? <ChevronUp size={15} color="var(--text-muted)" /> : <ChevronDown size={15} color="var(--text-muted)" />}
      </button>
      {expanded && (
        <div style={{ padding: "1rem 1.25rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {plan.summary && (
            <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", marginBottom: "0.5rem", lineHeight: 1.5 }}>
              <strong>Summary:</strong> {plan.summary}
            </p>
          )}
          {plan.actions.map((action, i) => (
            <div key={i} style={{
              padding: "0.5rem 0.75rem", borderRadius: "6px",
              background: "rgba(255,255,255,0.03)", border: "1px solid var(--border-glass)",
              fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.5rem",
            }}>
              <span style={{
                padding: "0.1rem 0.45rem", borderRadius: "4px", fontSize: "0.68rem",
                background: "rgba(99,102,241,0.2)", color: "#818cf8", fontWeight: 600, flexShrink: 0
              }}>{action.type}</span>
              <span style={{ color: "var(--text-secondary)" }}>{action.description}</span>
            </div>
          ))}
          {plan.files_affected?.length > 0 && (
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
              Files: {plan.files_affected.map(f => <code key={f} style={{ marginLeft: "0.3rem" }}>{f}</code>)}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────
function DesignStudio({ githubStatus, onConnectGithub, targetUrl, autoRun, onAutoRunConsumed }) {
  const [prompt, setPrompt] = useState("");
  const [generatedCss, setGeneratedCss] = useState("");
  const [running, setRunning] = useState(false);
  const [pipelineStage, setPipelineStage] = useState(null); // null | "interpret" | "bugdetect" | "generate" | "pr"
  const [progressPercent, setProgressPercent] = useState(0);
  const [subStatus, setSubStatus] = useState("");
  const [statusMsg, setStatusMsg] = useState(null);
  const [copied, setCopied] = useState(false);
  const [showCss, setShowCss] = useState(true);
  const [history, setHistory] = useState([]);
  const [detectedIntent, setDetectedIntent] = useState("design");
  const [actionPlan, setActionPlan] = useState(null);
  const [bugsDetected, setBugsDetected] = useState([]);
  const [prResult, setPrResult] = useState(null);
  const [createPr, setCreatePr] = useState(false);
  const [runBugScan, setRunBugScan] = useState(false);
  const [showBugs, setShowBugs] = useState(true);
  const textareaRef = useRef(null);

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = textareaRef.current.scrollHeight + "px";
    }
  }, [prompt]);

  // Auto-run when triggered from Dashboard "Scan URL"
  useEffect(() => {
    if (autoRun && autoRun.prompt && !running) {
      setPrompt(autoRun.prompt);
      setRunBugScan(!!autoRun.runBugScan);
      setDetectedIntent("both");
      // Small delay to let state settle before triggering pipeline
      const timer = setTimeout(() => {
        if (onAutoRunConsumed) onAutoRunConsumed();
        handleAutoRun(autoRun.prompt, !!autoRun.runBugScan);
      }, 400);
      return () => clearTimeout(timer);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun]);

  // Live intent detection as user types
  useEffect(() => {
    if (prompt.trim()) setDetectedIntent(detectIntent(prompt));
  }, [prompt]);

  const setStatus = (type, text, link) => setStatusMsg({ type, text, link });
  const clearStatus = () => setStatusMsg(null);

  const getRunningLabel = () => {
    if (pipelineStage === "interpret") return "Interpreting Prompt…";
    if (pipelineStage === "bugdetect") return "Scanning UI Bugs…";
    if (pipelineStage === "generate") return "Synthesizing CSS…";
    if (pipelineStage === "pr") return "Creating Pull Request…";
    return "Running Pipeline…";
  };

  // ── Auto-run pipeline (called from Dashboard with explicit args) ────────────
  const handleAutoRun = async (autoPrompt, autoRunBugScan) => {
    if (!autoPrompt?.trim() || running) return;
    setRunning(true);
    clearStatus();
    setGeneratedCss("");
    setActionPlan(null);
    setBugsDetected([]);
    setPrResult(null);

    const intent = detectIntent(autoPrompt);
    const needsBugScan = autoRunBugScan || intent === "bugfix" || intent === "both";

    setPipelineStage("interpret");
    setProgressPercent(15);
    setSubStatus("✨ Interpreting prompt intent & semantic UI architecture...");
    await sleep(1200);
    setProgressPercent(28);
    setSubStatus("🧠 Structuring action plan & identifying CSS target rules...");
    await sleep(1000);

    if (needsBugScan) {
      setPipelineStage("bugdetect");
      setProgressPercent(42);
      setSubStatus("🔍 Scanning DOM tree for layout regressions & contrast issues...");
      await sleep(1500);
      setProgressPercent(55);
      setSubStatus("🎯 Validating WCAG 2.1 accessibility & element bounding boxes...");
      await sleep(1000);
    }

    setPipelineStage("generate");
    setProgressPercent(needsBugScan ? 65 : 45);
    setSubStatus("🎨 Synthesizing modern glassmorphism & responsive CSS with Gemini...");

    const tickerSubMessages = [
      "🎨 Formulating surgical CSS selectors & scoped properties...",
      "✨ Applying dark-mode glassmorphism and ambient elevation shadows...",
      "📐 Verifying layout responsiveness across breakpoints...",
      "💎 Refining micro-interactions and smooth transition tokens...",
    ];
    let tickerIdx = 0;
    const tickerInterval = setInterval(() => {
      tickerIdx = (tickerIdx + 1) % tickerSubMessages.length;
      setSubStatus(tickerSubMessages[tickerIdx]);
      setProgressPercent((prev) => Math.min(prev + 5, 88));
    }, 2200);

    try {
      const res = await fetch(`${API_BASE}/design/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: autoPrompt,
          target_url: targetUrl || "",
          create_pr: false,
          run_bug_detection: needsBugScan,
        }),
      });
      clearInterval(tickerInterval);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Pipeline failed");

      setActionPlan(data.action_plan || null);
      setBugsDetected(data.bugs_detected || []);
      setGeneratedCss(data.css || "");
      setHistory((prev) => [{ prompt: autoPrompt, css: data.css, ts: new Date().toLocaleTimeString() }, ...prev.slice(0, 9)]);

      setProgressPercent(100);
      setSubStatus("✅ Design synthesized successfully!");
      await sleep(600);
      setStatus("success", `CSS generated successfully! Intent: ${data.intent}`);
    } catch (e) {
      clearInterval(tickerInterval);
      setStatus("error", e.message);
    } finally {
      setRunning(false);
      setPipelineStage(null);
      setProgressPercent(0);
      setSubStatus("");
    }
  };

  // ── Full pipeline ──────────────────────────────────────────
  const handleRun = async () => {
    if (!prompt.trim() || running) return;
    setRunning(true);
    clearStatus();
    setGeneratedCss("");
    setActionPlan(null);
    setBugsDetected([]);
    setPrResult(null);

    const intent = detectIntent(prompt);
    const needsBugScan = runBugScan || intent === "bugfix" || intent === "both";

    // Step 1: Interpret (visual smooth transition)
    setPipelineStage("interpret");
    setProgressPercent(15);
    setSubStatus("✨ Interpreting prompt intent & semantic UI architecture...");
    await sleep(1200);

    setProgressPercent(28);
    setSubStatus("🧠 Structuring action plan & identifying CSS target rules...");
    await sleep(1000);

    // Step 2: Bug scan phase display (if applicable)
    if (needsBugScan) {
      setPipelineStage("bugdetect");
      setProgressPercent(42);
      setSubStatus("🔍 Scanning DOM tree for layout regressions & contrast issues...");
      await sleep(1500);
      setProgressPercent(55);
      setSubStatus("🎯 Validating WCAG 2.1 accessibility & element bounding boxes...");
      await sleep(1000);
    }

    // Step 3: Generate CSS + run full pipeline
    setPipelineStage("generate");
    setProgressPercent(needsBugScan ? 65 : 45);
    setSubStatus("🎨 Synthesizing modern glassmorphism & responsive CSS with Gemini...");

    const tickerSubMessages = [
      "🎨 Formulating surgical CSS selectors & scoped properties...",
      "✨ Applying dark-mode glassmorphism and ambient elevation shadows...",
      "📐 Verifying layout responsiveness across breakpoints...",
      "💎 Refining micro-interactions and smooth transition tokens...",
    ];
    let tickerIdx = 0;
    const tickerInterval = setInterval(() => {
      tickerIdx = (tickerIdx + 1) % tickerSubMessages.length;
      setSubStatus(tickerSubMessages[tickerIdx]);
      setProgressPercent((prev) => Math.min(prev + 5, 88));
    }, 2200);

    try {
      const res = await fetch(`${API_BASE}/design/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          target_url: targetUrl || "",
          create_pr: createPr,
          run_bug_detection: needsBugScan,
        }),
      });
      clearInterval(tickerInterval);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Pipeline failed");

      setActionPlan(data.action_plan || null);
      setBugsDetected(data.bugs_detected || []);
      setGeneratedCss(data.css || "");
      setHistory((prev) => [{ prompt, css: data.css, ts: new Date().toLocaleTimeString() }, ...prev.slice(0, 9)]);

      // Step 4: PR
      if (createPr) {
        setPipelineStage("pr");
        setProgressPercent(94);
        setSubStatus("🚀 Packaging Git branch and pushing Pull Request to GitHub...");
        await sleep(1500);
        setProgressPercent(100);
        setSubStatus("✅ Pull request created successfully!");

        if (data.pr_url) {
          setPrResult(data);
          setStatus("success", `🚀 Pull Request #${data.pr_number} created!`, data.pr_url);
        } else {
          setStatus("success", "CSS generated! No PR was created (check GitHub connection).");
        }
      } else {
        setProgressPercent(100);
        setSubStatus("✅ Design synthesized successfully!");
        await sleep(600);
        setStatus("success", `CSS generated successfully! Intent: ${data.intent}`);
      }
    } catch (e) {
      clearInterval(tickerInterval);
      setStatus("error", e.message);
    } finally {
      setRunning(false);
      setPipelineStage(null);
      setProgressPercent(0);
      setSubStatus("");
    }
  };

  // ── Manual CSS → PR push ──────────────────────────────────
  const handlePushPr = async () => {
    if (!generatedCss) return;
    if (!githubStatus?.configured) { onConnectGithub?.(); return; }
    setRunning(true);
    setPipelineStage("pr");
    setProgressPercent(30);
    setSubStatus("Connecting to GitHub & packaging branch...");
    clearStatus();
    try {
      setProgressPercent(60);
      setSubStatus("Writing CSS patch & opening Pull Request...");
      const res = await fetch(`${API_BASE}/design/push`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ css: generatedCss, prompt, target_url: targetUrl || "" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Push failed");
      setProgressPercent(100);
      setSubStatus("Pull Request created successfully!");
      setPrResult(data);
      setStatus("success", `Pull Request #${data.pr_number} created on GitHub!`, data.pr_url);
    } catch (e) {
      setStatus("error", e.message);
    } finally {
      setRunning(false);
      setPipelineStage(null);
      setProgressPercent(0);
      setSubStatus("");
    }
  };

  const handleCopy = () => {
    if (!generatedCss) return;
    navigator.clipboard.writeText(generatedCss);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!generatedCss) return;
    const blob = new Blob([generatedCss], { type: "text/css" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "omnisight-design.css";
    document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(url); if (a.parentNode) document.body.removeChild(a); }, 60000);
  };

  const handleReset = () => {
    setGeneratedCss(""); setActionPlan(null); setBugsDetected([]);
    setPrResult(null); clearStatus(); setPrompt("");
  };

  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); if (!running) handleRun(); }
  };

  const intentMeta = INTENT_META[detectedIntent] || INTENT_META.design;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: "100%" }}>

      {/* ── Header ─────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
        <div style={{
          width: "48px", height: "48px", borderRadius: "12px",
          background: "linear-gradient(135deg, #6366f1, #3b82f6)",
          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          boxShadow: "0 4px 20px rgba(99,102,241,0.45)",
        }}>
          <Wand2 size={22} color="white" />
        </div>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: "1.375rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            AI Design Studio
          </h2>
          <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", margin: "0.2rem 0 0" }}>
            Describe any UI change or ask to fix bugs — Gemini will generate the code and optionally push a GitHub PR.
          </p>
        </div>

        {/* Target URL display */}
        {targetUrl && (
          <div style={{
            display: "flex", alignItems: "center", gap: "0.5rem",
            padding: "0.45rem 0.875rem", borderRadius: "8px",
            background: "rgba(255,255,255,0.04)", border: "1px solid var(--border-glass)",
            fontSize: "0.78rem", color: "var(--text-secondary)", maxWidth: "320px",
          }}>
            <Globe size={13} color="var(--accent-primary)" />
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {targetUrl}
            </span>
            <a href={targetUrl} target="_blank" rel="noopener noreferrer"
              style={{ color: "var(--text-muted)", flexShrink: 0 }}>
              <ExternalLink size={12} />
            </a>
          </div>
        )}
      </div>

      {/* ── Prompt Area ────────────────────────────────────── */}
      <div className="glass-panel" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <label style={{
          fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)",
          textTransform: "uppercase", letterSpacing: "0.06em",
        }}>
          Your Design Prompt
        </label>

        {/* Live intent badge */}
        {prompt.trim() && (
          <div style={{
            display: "inline-flex", alignItems: "center", gap: "0.4rem",
            padding: "0.25rem 0.75rem", borderRadius: "20px", fontSize: "0.75rem",
            background: intentMeta.bg, border: `1px solid ${intentMeta.border}`,
            color: intentMeta.color, fontWeight: 600, width: "fit-content",
          }}>
            {intentMeta.label}
            <span style={{ fontWeight: 400, color: "inherit", opacity: 0.8 }}>— {intentMeta.desc}</span>
          </div>
        )}

        {/* Textarea */}
        <div style={{ position: "relative" }}>
          <textarea
            ref={textareaRef}
            id="design-studio-prompt"
            placeholder={`e.g. "Make the hero section a two-column glassmorphism layout with cyan accents"\nor "Detect and fix all low-contrast text issues on the page"`}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={3}
            style={{
              width: "100%", padding: "0.9rem 3rem 0.9rem 1rem", borderRadius: "10px",
              border: "1px solid var(--border-glass)", background: "rgba(255,255,255,0.04)",
              color: "var(--text-primary)", fontSize: "0.9rem", fontFamily: "inherit",
              resize: "none", outline: "none", lineHeight: 1.6, overflow: "hidden",
              transition: "border-color 0.2s, box-shadow 0.2s",
              boxSizing: "border-box",
            }}
            onFocus={e => { e.target.style.borderColor = "var(--accent-primary)"; e.target.style.boxShadow = "0 0 0 3px rgba(99,102,241,0.15)"; }}
            onBlur={e => { e.target.style.borderColor = "var(--border-glass)"; e.target.style.boxShadow = "none"; }}
          />
          {prompt && (
            <button onClick={() => setPrompt("")} title="Clear" style={{
              position: "absolute", top: "0.65rem", right: "0.65rem",
              background: "none", border: "none", cursor: "pointer",
              color: "var(--text-muted)", padding: "0.2rem", display: "flex",
            }}>
              <Trash2 size={15} />
            </button>
          )}
        </div>

        {/* Suggestion chips */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => setPrompt(s)} title={s} style={{
              padding: "0.3rem 0.75rem", borderRadius: "20px", fontSize: "0.72rem",
              border: "1px solid var(--border-glass)", background: "rgba(99,102,241,0.08)",
              color: "var(--text-secondary)", cursor: "pointer", fontFamily: "inherit",
              transition: "all 0.15s", whiteSpace: "nowrap", overflow: "hidden",
              textOverflow: "ellipsis", maxWidth: "270px",
            }}
              onMouseOver={e => { e.currentTarget.style.background = "rgba(99,102,241,0.2)"; e.currentTarget.style.color = "var(--text-primary)"; }}
              onMouseOut={e => { e.currentTarget.style.background = "rgba(99,102,241,0.08)"; e.currentTarget.style.color = "var(--text-secondary)"; }}
            >
              {s.length > 44 ? s.slice(0, 44) + "…" : s}
            </button>
          ))}
        </div>

        {/* Options row */}
        <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap", alignItems: "center" }}>
          {[
            { id: "createPr", label: "Auto-create GitHub PR", state: createPr, set: setCreatePr, icon: <GitPullRequest size={13} /> },
            { id: "runBugScan", label: "Also scan for UI bugs", state: runBugScan, set: setRunBugScan, icon: <Bug size={13} /> },
          ].map(({ id, label, state, set, icon }) => (
            <label key={id} htmlFor={id} style={{
              display: "flex", alignItems: "center", gap: "0.4rem",
              fontSize: "0.8rem", color: "var(--text-secondary)", cursor: "pointer",
            }}>
              <input
                id={id} type="checkbox" checked={state}
                onChange={e => set(e.target.checked)}
                style={{ accentColor: "var(--accent-primary)", width: "14px", height: "14px" }}
              />
              {icon}
              {label}
            </label>
          ))}
        </div>

        {/* Action buttons */}
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
          <button
            id="design-studio-run-btn"
            onClick={handleRun}
            disabled={running || !prompt.trim()}
            className={`btn btn-primary ${running ? "studio-running-btn" : ""}`}
            style={{
              padding: "0.75rem 1.5rem", fontSize: "0.9rem", fontWeight: 600,
              display: "flex", alignItems: "center", gap: "0.6rem",
              background: running ? undefined : "linear-gradient(135deg, #6366f1, #3b82f6)",
              boxShadow: running ? "0 0 25px rgba(99,102,241,0.55)" : "0 4px 16px rgba(99,102,241,0.35)",
              transition: "all 0.3s ease",
            }}
          >
            {running ? (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: "2.5px", height: "14px" }}>
                  <span style={{ width: "3px", borderRadius: "1px", background: "white", animation: "soundWaveBar 1.2s infinite ease-in-out" }} />
                  <span style={{ width: "3px", borderRadius: "1px", background: "white", animation: "soundWaveBar 1.2s infinite ease-in-out 0.25s" }} />
                  <span style={{ width: "3px", borderRadius: "1px", background: "white", animation: "soundWaveBar 1.2s infinite ease-in-out 0.5s" }} />
                </div>
                <span>{getRunningLabel()}</span>
              </>
            ) : (
              <>
                <Sparkles size={16} />
                <span>Run Design Studio</span>
              </>
            )}
          </button>
          {generatedCss && !running && (
            <button onClick={handleReset} className="btn btn-secondary"
              style={{ padding: "0.75rem 1rem", fontSize: "0.875rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <RotateCcw size={14} /> Reset
            </button>
          )}
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.35rem" }}>
            {running ? (
              <>
                <span style={{
                  width: "6px", height: "6px", borderRadius: "50%",
                  background: "#38bdf8", display: "inline-block",
                  animation: "liveBeaconPing 1.5s infinite"
                }} />
                AI Studio processing…
              </>
            ) : "Ctrl+Enter to run"}
          </span>
        </div>
      </div>

      {/* ── Pipeline progress ───────────────────────────────── */}
      {running && pipelineStage && (
        <PipelineProgress
          stage={pipelineStage}
          subStatus={subStatus}
          progressPercent={progressPercent}
        />
      )}

      {/* ── Status banner ───────────────────────────────────── */}
      <StatusBanner msg={statusMsg} onClose={clearStatus} />

      {/* ── PR Result ───────────────────────────────────────── */}
      {prResult?.pr_url && (
        <div style={{
          padding: "1rem 1.25rem", borderRadius: "10px",
          background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.3)",
          display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap",
        }}>
          <CheckCircle2 size={20} color="#10b981" />
          <div style={{ flex: 1 }}>
            <p style={{ fontWeight: 600, color: "#34d399", margin: 0, fontSize: "0.9rem" }}>
              Pull Request #{prResult.pr_number} created
            </p>
            <p style={{ color: "var(--text-muted)", margin: "0.15rem 0 0", fontSize: "0.78rem" }}>
              Branch: <code>{prResult.branch}</code> · File: <code>{prResult.file}</code>
            </p>
          </div>
          <a href={prResult.pr_url} target="_blank" rel="noopener noreferrer"
            className="btn btn-primary"
            style={{ padding: "0.5rem 1rem", fontSize: "0.82rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
            View PR <ExternalLink size={13} />
          </a>
        </div>
      )}

      {/* ── Action Plan ─────────────────────────────────────── */}
      {actionPlan && <ActionPlanCard plan={actionPlan} />}

      {/* ── Detected Bugs ───────────────────────────────────── */}
      {bugsDetected.length > 0 && (
        <div className="glass-panel" style={{ overflow: "hidden" }}>
          <button onClick={() => setShowBugs(v => !v)} style={{
            width: "100%", padding: "0.875rem 1.25rem",
            display: "flex", alignItems: "center", justifyContent: "space-between",
            background: "none", border: "none", cursor: "pointer",
            borderBottom: showBugs ? "1px solid var(--border-glass)" : "none",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
              <Bug size={15} color="#f59e0b" />
              <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>
                Detected Bugs
                <span style={{ marginLeft: "0.5rem", padding: "0.1rem 0.5rem", borderRadius: "20px", background: "rgba(245,158,11,0.2)", color: "#fbbf24", fontSize: "0.72rem" }}>
                  {bugsDetected.length}
                </span>
              </span>
            </div>
            {showBugs ? <ChevronUp size={15} color="var(--text-muted)" /> : <ChevronDown size={15} color="var(--text-muted)" />}
          </button>
          {showBugs && (
            <div style={{ padding: "1rem 1.25rem", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
              {bugsDetected.map((bug, i) => <BugCard key={i} bug={bug} idx={i} />)}
            </div>
          )}
        </div>
      )}

      {/* ── Generated CSS Panel ─────────────────────────────── */}
      {generatedCss && (
        <div className="glass-panel" style={{ overflow: "hidden" }}>
          {/* Panel header */}
          <div style={{
            padding: "0.875rem 1.25rem", borderBottom: "1px solid var(--border-glass)",
            display: "flex", alignItems: "center", gap: "0.75rem",
          }}>
            <div style={{ width: "8px", height: "8px", borderRadius: "50%", background: "var(--success)", boxShadow: "0 0 8px var(--success)" }} />
            <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)", flex: 1 }}>
              Generated CSS{" "}
              <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>({generatedCss.length} chars)</span>
            </span>
            <div style={{ display: "flex", gap: "0.4rem" }}>
              <button onClick={handleCopy} className="btn btn-secondary" style={{ padding: "0.35rem 0.75rem", fontSize: "0.78rem" }}>
                {copied ? <Check size={13} /> : <Copy size={13} />}
                {copied ? "Copied!" : "Copy"}
              </button>
              <button onClick={handleDownload} className="btn btn-secondary" style={{ padding: "0.35rem 0.75rem", fontSize: "0.78rem" }}>
                ⬇ Download
              </button>
              <button onClick={() => setShowCss(v => !v)} className="btn btn-secondary" style={{ padding: "0.35rem 0.75rem", fontSize: "0.78rem" }}>
                {showCss ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                {showCss ? "Collapse" : "Expand"}
              </button>
            </div>
          </div>

          {/* CSS code */}
          {showCss && (
            <pre style={{
              margin: 0, padding: "1.25rem", overflowX: "auto",
              fontSize: "0.8rem", lineHeight: 1.65,
              color: "#a5f3fc", background: "rgba(0,0,0,0.25)",
              fontFamily: "'JetBrains Mono', 'Fira Code', 'Courier New', monospace",
              maxHeight: "420px", overflowY: "auto",
            }}>
              {generatedCss}
            </pre>
          )}

          {/* Push to GitHub */}
          <div style={{
            padding: "1rem 1.25rem", borderTop: "1px solid var(--border-glass)",
            display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap",
          }}>
            <button
              id="design-studio-push-btn"
              onClick={handlePushPr}
              disabled={running}
              className="btn btn-primary"
              style={{
                padding: "0.7rem 1.4rem", fontSize: "0.9rem", fontWeight: 600,
                background: "linear-gradient(135deg, #10b981, #059669)",
                display: "flex", alignItems: "center", gap: "0.5rem",
              }}
            >
              {running ? <Loader2 size={16} className="animate-spin" /> : <GitPullRequest size={16} />}
              {running ? "Pushing to GitHub…" : githubStatus?.configured ? "🚀 Push to GitHub PR" : "Connect GitHub to Push"}
            </button>
            {!githubStatus?.configured && (
              <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                → <button onClick={onConnectGithub} style={{
                  background: "none", border: "none", cursor: "pointer",
                  color: "var(--accent-primary)", fontSize: "0.78rem", fontFamily: "inherit",
                }}>Connect GitHub</button> to enable 1-click PRs
              </span>
            )}
          </div>
        </div>
      )}

      {/* ── Prompt History ──────────────────────────────────── */}
      {history.length > 0 && (
        <div className="glass-panel" style={{ padding: "1.25rem" }}>
          <h3 style={{
            fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)",
            marginBottom: "0.75rem", textTransform: "uppercase", letterSpacing: "0.06em",
          }}>
            Recent Prompts
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {history.map((h, i) => (
              <button key={i} onClick={() => { setPrompt(h.prompt); setGeneratedCss(h.css); clearStatus(); }} style={{
                textAlign: "left", padding: "0.6rem 0.875rem", borderRadius: "8px",
                border: "1px solid var(--border-glass)", background: "rgba(255,255,255,0.02)",
                color: "var(--text-secondary)", fontSize: "0.82rem", cursor: "pointer",
                fontFamily: "inherit", display: "flex", justifyContent: "space-between",
                alignItems: "center", transition: "background 0.15s",
              }}
                onMouseOver={e => e.currentTarget.style.background = "rgba(99,102,241,0.08)"}
                onMouseOut={e => e.currentTarget.style.background = "rgba(255,255,255,0.02)"}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "85%" }}>
                  {h.prompt}
                </span>
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", flexShrink: 0 }}>{h.ts}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default DesignStudio;
