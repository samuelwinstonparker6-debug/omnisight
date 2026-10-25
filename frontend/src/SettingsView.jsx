import { useState } from "react";
import { Sun, Moon, Palette, CheckCircle2, Trash2, RefreshCw, Zap, AlertCircle } from "lucide-react";

const API_BASE = typeof window !== "undefined" && (window.location.port === "5173" || window.location.port === "8000")
  ? "/api/v1"
  : "http://127.0.0.1:8000/api/v1";

export default function SettingsView({ theme, onThemeChange }) {
  const isDark = theme === "dark";
  const [clearing, setClearing] = useState(false);
  const [clearResult, setClearResult] = useState(null);

  const handleClearCache = async () => {
    if (clearing) return;
    setClearing(true);
    setClearResult(null);
    try {
      // 1. Call backend cache purge
      const res = await fetch(`${API_BASE}/system/clear-cache`, {
        method: "POST",
      });
      const data = await res.json();

      // 2. Clear browser performance entries & sessionStorage
      if (typeof window !== "undefined") {
        try {
          if (window.performance && window.performance.clearResourceTimings) {
            window.performance.clearResourceTimings();
          }
          sessionStorage.clear();
          // Clean legacy temp items from localStorage if any, keeping essential configs
          const targetUrl = localStorage.getItem("omnisight_target_url");
          const savedTheme = localStorage.getItem("omnisight_theme");
          const ghToken = localStorage.getItem("omnisight_github_token");
          const ghRepo = localStorage.getItem("omnisight_github_repo");
          localStorage.clear();
          if (targetUrl) localStorage.setItem("omnisight_target_url", targetUrl);
          if (savedTheme) localStorage.setItem("omnisight_theme", savedTheme);
          if (ghToken) localStorage.setItem("omnisight_github_token", ghToken);
          if (ghRepo) localStorage.setItem("omnisight_github_repo", ghRepo);
        } catch {
          // ignore storage clearing limitations
        }
      }

      setClearResult({
        success: true,
        message: data.message || "Cache and temporary files cleared successfully!",
        freedKb: data.freed_kb || 0,
        cleanedCount: data.cleaned_items_count || 0,
      });
    } catch (err) {
      setClearResult({
        success: false,
        message: err.message || "Failed to clear system cache.",
      });
    } finally {
      setClearing(false);
    }
  };

  return (
    <div style={{ maxWidth: "960px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "2rem" }}>
      {/* Header Banner */}
      <div
        className="glass-panel"
        style={{
          padding: "2rem 2.5rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: isDark
            ? "linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(22, 25, 37, 0.8))"
            : "linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(255, 255, 255, 0.9))",
          borderRadius: "16px",
          border: "1px solid var(--border-glass)",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.5rem" }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: "36px",
                height: "36px",
                borderRadius: "10px",
                background: "rgba(99, 102, 241, 0.2)",
                color: "var(--accent-primary)",
              }}
            >
              <Palette size={20} />
            </span>
            <h2 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)" }}>
              Appearance & Environment
            </h2>
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.92rem", maxWidth: "560px" }}>
            Customize the look and visual theme of the entire OmniSight console. Switches instantly across all views.
          </p>
        </div>

        <div
          style={{
            padding: "0.5rem 1rem",
            borderRadius: "9999px",
            background: isDark ? "rgba(99, 102, 241, 0.15)" : "rgba(245, 158, 11, 0.15)",
            border: `1px solid ${isDark ? "rgba(99, 102, 241, 0.3)" : "rgba(245, 158, 11, 0.3)"}`,
            color: isDark ? "#818cf8" : "#d97706",
            fontSize: "0.82rem",
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            gap: "0.45rem",
          }}
        >
          {isDark ? <Moon size={14} /> : <Sun size={14} />}
          <span>{isDark ? "Dark Theme Active" : "Light Theme Active"}</span>
        </div>
      </div>

      {/* Main Theme Control Card */}
      <div
        className="glass-panel"
        style={{
          padding: "2.25rem",
          display: "flex",
          flexDirection: "column",
          gap: "1.75rem",
          borderRadius: "16px",
        }}
      >
        <div>
          <h3 style={{ fontSize: "1.2rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.35rem" }}>
            Theme Mode
          </h3>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
            Choose between Light mode and Dark mode. Toggle animates seamlessly with instantaneous rendering.
          </p>
        </div>

        {/* ── Interactive Drawing Toggle Bar ── */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "1.25rem 1.75rem",
            background: isDark ? "rgba(0, 0, 0, 0.3)" : "rgba(0, 0, 0, 0.03)",
            borderRadius: "14px",
            border: "1px solid var(--border-glass)",
            flexWrap: "wrap",
            gap: "1.25rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            {/* Mode labels & indicator */}
            <div
              onClick={() => onThemeChange("light")}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                cursor: "pointer",
                padding: "0.5rem 0.85rem",
                borderRadius: "8px",
                transition: "all 0.2s ease",
                background: !isDark ? "rgba(245, 158, 11, 0.15)" : "transparent",
                color: !isDark ? "#d97706" : "var(--text-muted)",
                fontWeight: !isDark ? 600 : 500,
              }}
            >
              <Sun size={18} />
              <span>Light Mode</span>
            </div>

            {/* ── Seamless Animated Drawing Toggle Switch ── */}
            <button
              type="button"
              role="switch"
              aria-checked={isDark}
              aria-label="Toggle theme mode"
              onClick={() => onThemeChange(isDark ? "light" : "dark")}
              style={{
                position: "relative",
                width: "82px",
                height: "42px",
                borderRadius: "9999px",
                border: isDark ? "2px solid #6366f1" : "2px solid #f59e0b",
                background: isDark
                  ? "linear-gradient(135deg, #1e1b4b, #312e81)"
                  : "linear-gradient(135deg, #fef3c7, #fde68a)",
                cursor: "pointer",
                padding: 0,
                outline: "none",
                transition: "background 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease",
                boxShadow: isDark
                  ? "0 0 16px rgba(99, 102, 241, 0.4), inset 0 2px 4px rgba(0,0,0,0.5)"
                  : "0 0 16px rgba(245, 158, 11, 0.4), inset 0 2px 4px rgba(255,255,255,0.7)",
              }}
            >
              {/* Background ambient stars (dark) / sunshine rays (light) */}
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  borderRadius: "9999px",
                  overflow: "hidden",
                  pointerEvents: "none",
                }}
              >
                {isDark ? (
                  <>
                    <span style={{ position: "absolute", top: "8px", left: "14px", width: "2px", height: "2px", background: "#fff", borderRadius: "50%", opacity: 0.8 }} />
                    <span style={{ position: "absolute", bottom: "9px", left: "24px", width: "3px", height: "3px", background: "#cbd5e1", borderRadius: "50%", opacity: 0.9 }} />
                    <span style={{ position: "absolute", top: "18px", left: "20px", width: "1.5px", height: "1.5px", background: "#e0e7ff", borderRadius: "50%", opacity: 0.6 }} />
                  </>
                ) : (
                  <>
                    <span style={{ position: "absolute", top: "10px", right: "18px", width: "3px", height: "3px", background: "#f59e0b", borderRadius: "50%", opacity: 0.7 }} />
                    <span style={{ position: "absolute", bottom: "11px", right: "26px", width: "2.5px", height: "2.5px", background: "#d97706", borderRadius: "50%", opacity: 0.8 }} />
                  </>
                )}
              </div>

              {/* Moving circular thumb knob */}
              <div
                style={{
                  position: "absolute",
                  top: "3px",
                  left: isDark ? "43px" : "3px",
                  width: "32px",
                  height: "32px",
                  borderRadius: "50%",
                  background: isDark
                    ? "linear-gradient(135deg, #6366f1, #4f46e5)"
                    : "linear-gradient(135deg, #fbbf24, #f59e0b)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#ffffff",
                  boxShadow: isDark
                    ? "0 2px 8px rgba(0, 0, 0, 0.4), 0 0 10px rgba(99, 102, 241, 0.8)"
                    : "0 2px 8px rgba(245, 158, 11, 0.4), 0 0 10px rgba(251, 191, 36, 0.8)",
                  transition: "left 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), background 0.25s ease, transform 0.2s ease",
                  transform: "scale(1)",
                }}
              >
                {isDark ? (
                  <Moon size={16} color="#ffffff" style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.5))" }} />
                ) : (
                  <Sun size={17} color="#ffffff" style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.3))" }} />
                )}
              </div>
            </button>

            <div
              onClick={() => onThemeChange("dark")}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                cursor: "pointer",
                padding: "0.5rem 0.85rem",
                borderRadius: "8px",
                transition: "all 0.2s ease",
                background: isDark ? "rgba(99, 102, 241, 0.15)" : "transparent",
                color: isDark ? "#818cf8" : "var(--text-muted)",
                fontWeight: isDark ? 600 : 500,
              }}
            >
              <Moon size={18} />
              <span>Dark Mode</span>
            </div>
          </div>

          {/* Quick preset selector cards */}
          <div style={{ display: "flex", gap: "0.75rem" }}>
            <button
              onClick={() => onThemeChange("light")}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "8px",
                border: !isDark ? "2px solid #f59e0b" : "1px solid var(--border-glass)",
                background: !isDark ? "rgba(245, 158, 11, 0.1)" : "transparent",
                color: !isDark ? "var(--text-primary)" : "var(--text-secondary)",
                cursor: "pointer",
                fontWeight: 500,
                fontSize: "0.82rem",
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
                transition: "all 0.15s ease",
              }}
            >
              <Sun size={14} color={!isDark ? "#f59e0b" : "inherit"} />
              Light
              {!isDark && <CheckCircle2 size={13} color="#f59e0b" />}
            </button>

            <button
              onClick={() => onThemeChange("dark")}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "8px",
                border: isDark ? "2px solid var(--accent-primary)" : "1px solid var(--border-glass)",
                background: isDark ? "rgba(99, 102, 241, 0.12)" : "transparent",
                color: isDark ? "var(--text-primary)" : "var(--text-secondary)",
                cursor: "pointer",
                fontWeight: 500,
                fontSize: "0.82rem",
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
                transition: "all 0.15s ease",
              }}
            >
              <Moon size={14} color={isDark ? "var(--accent-primary)" : "inherit"} />
              Dark
              {isDark && <CheckCircle2 size={13} color="var(--accent-primary)" />}
            </button>
          </div>
        </div>

        {/* Live Preview Comparison Cards */}
        <div>
          <h4 style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.85rem" }}>
            Visual Scheme Preview
          </h4>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1rem" }}>
            {/* Light Mode Preview */}
            <div
              onClick={() => onThemeChange("light")}
              style={{
                cursor: "pointer",
                padding: "1.25rem",
                borderRadius: "12px",
                background: "#f8fafc",
                border: !isDark ? "2px solid #f59e0b" : "1px solid #e2e8f0",
                boxShadow: !isDark ? "0 0 15px rgba(245, 158, 11, 0.3)" : "none",
                transition: "all 0.2s ease",
                display: "flex",
                flexDirection: "column",
                gap: "0.75rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontWeight: 600, fontSize: "0.88rem", color: "#0f172a", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <Sun size={15} color="#f59e0b" />
                  Daylight Crisp
                </span>
                {!isDark && (
                  <span style={{ fontSize: "0.7rem", padding: "0.15rem 0.5rem", borderRadius: "9999px", background: "#fef3c7", color: "#b45309", fontWeight: 600 }}>
                    ACTIVE
                  </span>
                )}
              </div>
              <div style={{ padding: "0.75rem", borderRadius: "8px", background: "#ffffff", border: "1px solid #e2e8f0", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                <div style={{ height: "8px", width: "60%", background: "#6366f1", borderRadius: "4px" }} />
                <div style={{ height: "6px", width: "90%", background: "#cbd5e1", borderRadius: "3px" }} />
                <div style={{ height: "6px", width: "75%", background: "#e2e8f0", borderRadius: "3px" }} />
              </div>
              <span style={{ fontSize: "0.75rem", color: "#64748b" }}>
                High readability in well-lit workspaces with crisp high-contrast surfaces.
              </span>
            </div>

            {/* Dark Mode Preview */}
            <div
              onClick={() => onThemeChange("dark")}
              style={{
                cursor: "pointer",
                padding: "1.25rem",
                borderRadius: "12px",
                background: "#0f111a",
                border: isDark ? "2px solid var(--accent-primary)" : "1px solid rgba(255,255,255,0.08)",
                boxShadow: isDark ? "0 0 15px rgba(99, 102, 241, 0.3)" : "none",
                transition: "all 0.2s ease",
                display: "flex",
                flexDirection: "column",
                gap: "0.75rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontWeight: 600, fontSize: "0.88rem", color: "#f8fafc", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <Moon size={15} color="#818cf8" />
                  Midnight Cyber
                </span>
                {isDark && (
                  <span style={{ fontSize: "0.7rem", padding: "0.15rem 0.5rem", borderRadius: "9999px", background: "rgba(99,102,241,0.2)", color: "#a5b4fc", fontWeight: 600 }}>
                    ACTIVE
                  </span>
                )}
              </div>
              <div style={{ padding: "0.75rem", borderRadius: "8px", background: "#161925", border: "1px solid rgba(255,255,255,0.08)", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                <div style={{ height: "8px", width: "60%", background: "#6366f1", borderRadius: "4px" }} />
                <div style={{ height: "6px", width: "90%", background: "rgba(255,255,255,0.15)", borderRadius: "3px" }} />
                <div style={{ height: "6px", width: "75%", background: "rgba(255,255,255,0.08)", borderRadius: "3px" }} />
              </div>
              <span style={{ fontSize: "0.75rem", color: "#94a3b8" }}>
                Low eye strain with OLED obsidian tones, neon accents, and subtle glassmorphism.
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ── Clear Cache & System Optimization Section ── */}
      <div
        className="glass-panel"
        style={{
          padding: "2rem 2.25rem",
          display: "flex",
          flexDirection: "column",
          gap: "1.25rem",
          borderRadius: "16px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.55rem", marginBottom: "0.35rem" }}>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: "30px",
                  height: "30px",
                  borderRadius: "8px",
                  background: "rgba(239, 68, 68, 0.15)",
                  color: "#ef4444",
                }}
              >
                <Trash2 size={16} />
              </span>
              <h3 style={{ fontSize: "1.15rem", fontWeight: 600, color: "var(--text-primary)" }}>
                Clear Temporary Files & Cache
              </h3>
            </div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", maxWidth: "620px" }}>
              Purges temporary viewport screenshots, fixed code patches, server logs, browser resource timings, and Python bytecode caches. Accelerates scan execution and frees local disk space.
            </p>
          </div>

          <button
            onClick={handleClearCache}
            disabled={clearing}
            className="btn"
            style={{
              padding: "0.7rem 1.4rem",
              borderRadius: "10px",
              background: isDark
                ? "linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(220, 38, 38, 0.35))"
                : "linear-gradient(135deg, #fee2e2, #fecaca)",
              border: "1px solid rgba(239, 68, 68, 0.4)",
              color: isDark ? "#fca5a5" : "#b91c1c",
              fontWeight: 600,
              fontSize: "0.875rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              cursor: clearing ? "not-allowed" : "pointer",
              transition: "all 0.2s ease",
              boxShadow: "0 4px 12px rgba(239, 68, 68, 0.15)",
            }}
          >
            {clearing ? (
              <>
                <RefreshCw size={16} className="animate-spin" />
                <span>Purging Cache...</span>
              </>
            ) : (
              <>
                <Zap size={16} />
                <span>Clear Cache Now</span>
              </>
            )}
          </button>
        </div>

        {/* Clear Result Feedback Message */}
        {clearResult && (
          <div
            className="animate-fade-in"
            style={{
              padding: "0.9rem 1.25rem",
              borderRadius: "10px",
              fontSize: "0.85rem",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "1rem",
              background: clearResult.success
                ? "rgba(16, 185, 129, 0.12)"
                : "rgba(239, 68, 68, 0.12)",
              border: `1px solid ${
                clearResult.success ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)"
              }`,
              color: clearResult.success ? "#34d399" : "#f87171",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
              {clearResult.success ? (
                <CheckCircle2 size={16} color="#34d399" />
              ) : (
                <AlertCircle size={16} color="#f87171" />
              )}
              <span>{clearResult.message}</span>
            </div>

            {clearResult.success && clearResult.cleanedCount > 0 && (
              <span
                style={{
                  fontSize: "0.75rem",
                  padding: "0.2rem 0.6rem",
                  borderRadius: "9999px",
                  background: "rgba(16, 185, 129, 0.2)",
                  fontWeight: 600,
                  whiteSpace: "nowrap",
                }}
              >
                Freed {clearResult.freedKb} KB ({clearResult.cleanedCount} items removed)
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
