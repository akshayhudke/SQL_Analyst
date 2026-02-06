import { useEffect, useMemo, useRef, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const sampleQueries = [
  "SELECT c.region, COUNT(*) AS orders FROM orders o JOIN customers c ON c.id = o.customer_id WHERE o.status = 'shipped' GROUP BY c.region ORDER BY orders DESC",
  "SELECT * FROM orders WHERE status = 'pending' ORDER BY ordered_at DESC",
];

/** Format milliseconds for display. */
function formatMs(value) {
  if (value === null || value === undefined) return "n/a";
  return `${Number(value).toFixed(2)} ms`;
}

/** Format requests per minute for display. */
function formatRate(value) {
  if (value === null || value === undefined) return "n/a";
  return `${value}/min`;
}

/** Show an optimization score as N/100. */
function formatScore(value) {
  if (value === null || value === undefined) return "n/a";
  return `${value}/100`;
}

/** Simple titled section used in several cards. */
function Section({ title, children }) {
  return (
    <div className="section">
      <div className="section-title">{title}</div>
      <div className="section-body">{children}</div>
    </div>
  );
}

/** Small pill showing agent health status. */
function StatusPill({ status, label }) {
  const tone =
    status === "ok" ? "status-ok" : status === "down" ? "status-down" : "status-warn";
  return (
    <div className={`status-pill ${tone}`}>
      <span className="status-dot" />
      <span>{label}</span>
    </div>
  );
}

/** Metric box used in the left rail. */
function MetricCard({ label, value, hint }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {hint && <div className="metric-hint">{hint}</div>}
    </div>
  );
}

function TrendChart({ data }) {
  if (!data || data.length === 0) {
    return <div className="note">No trend data yet.</div>;
  }
  const width = 360;
  const height = 120;
  const padding = 18;
  const scores = data.map((d) => d.avg_score ?? 0);
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const range = max - min || 1;
  const points = data.map((d, i) => {
    const x =
      padding + (i / Math.max(1, data.length - 1)) * (width - padding * 2);
    const y =
      height -
      padding -
      ((d.avg_score ?? 0) - min) / range * (height - padding * 2);
    return `${x},${y}`;
  });

  return (
    <svg className="trend-chart" viewBox={`0 0 ${width} ${height}`}>
      <polyline points={points.join(" ")} />
    </svg>
  );
}

/** Main analysis block with cards, suggestions, and diff view. */
function AnalysisPanel({ data }) {
  const [showDiff, setShowDiff] = useState(false);
  const originalSql = data.original_sql || "";
  const suggestedSql = data.llm?.suggested_sql || "";

  const diffLines = useMemo(() => {
    const left = originalSql.split("\n");
    const right = suggestedSql.split("\n");
    const max = Math.max(left.length, right.length);
    const rows = [];
    for (let i = 0; i < max; i += 1) {
      rows.push({
        left: left[i] ?? "",
        right: right[i] ?? "",
        changed: (left[i] ?? "") !== (right[i] ?? ""),
      });
    }
    return rows;
  }, [originalSql, suggestedSql]);

  if (!data) return null;

  const whySlow = data.insights?.why_slow || [];
  const indexRecs = data.insights?.index_recommendations || [];
  const score = data.insights?.optimization_score || {};

  return (
    <div className="analysis-stack">
      {score && score.score !== undefined && (
        <div className="analysis-card">
          <div className="card-header">
            <div>Optimization Score</div>
            <div className="score-grade">{score.grade || "n/a"}</div>
          </div>
          <div className="score-value">{formatScore(score.score)}</div>
          <div className="score-bar">
            <div className="score-fill" style={{ width: `${score.score || 0}%` }} />
          </div>
          <div className="note">
            Issues detected: {score.issue_count ?? 0}
          </div>
        </div>
      )}

      <div className="analysis-card">
        <div className="card-header">Why This Query Is Slow</div>
        {whySlow.length === 0 ? (
          <div className="note">No high-severity issues detected.</div>
        ) : (
          <ul className="card-list">
            {whySlow.map((item, idx) => (
              <li key={`${item.title}-${idx}`}>
                <strong>[S{item.severity}] {item.title}</strong> — {item.rationale}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="analysis-card">
        <div className="card-header">
          <div>Optimized Query</div>
          {suggestedSql && (
            <div className="card-actions">
              <button
                type="button"
                className="ghost"
                onClick={() => navigator.clipboard.writeText(suggestedSql)}
              >
                Copy SQL
              </button>
              <button
                type="button"
                className="ghost"
                onClick={() => setShowDiff((prev) => !prev)}
              >
                {showDiff ? "Hide Diff" : "Show Diff"}
              </button>
            </div>
          )}
        </div>
        {data.llm && data.llm.error && <div className="note">LLM issue: {data.llm.error}</div>}
        {suggestedSql ? (
          <div className="code-block">
            <pre>{suggestedSql}</pre>
          </div>
        ) : (
          <div className="note">No safe rewrite suggested yet.</div>
        )}
        {showDiff && suggestedSql && (
          <div className="diff-view">
            <div className="diff-header">
              <span>Original</span>
              <span>Optimized</span>
            </div>
            <div className="diff-grid">
              {diffLines.map((row, idx) => (
                <div key={idx} className={`diff-row ${row.changed ? "changed" : ""}`}>
                  <div className="diff-cell">{row.left}</div>
                  <div className="diff-cell">{row.right}</div>
                </div>
              ))}
            </div>
          </div>
        )}
        {data.llm?.model_used && <div className="note">Model: {data.llm.model_used}</div>}
        {data.llm?.rewrite_source && (
          <div className="note">Rewrite source: {data.llm.rewrite_source}</div>
        )}
      </div>

      <div className="analysis-card">
        <div className="card-header">Index Recommendations</div>
        {indexRecs.length === 0 ? (
          <div className="note">No index recommendations available yet.</div>
        ) : (
          <ul className="card-list">
            {indexRecs.map((rec, idx) => (
              <li key={`${rec.statement}-${idx}`}>
                <code>{rec.statement}</code>
                <div className="note">{rec.rationale}</div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {data.warnings && data.warnings.length > 0 && (
        <Section title="Warnings">
          <ul>
            {data.warnings.map((warning, idx) => (
              <li key={idx}>{warning}</li>
            ))}
          </ul>
        </Section>
      )}

      {data.llm && (
        <Section title="LLM Explanation">
          <div className="text-block">
            {data.llm.explanation || "No explanation yet."}
          </div>
          {data.llm.recommendation_rationale && (
            <div className="text-block">{data.llm.recommendation_rationale}</div>
          )}
          <div className="note">LLM output is explanation-only and never executed.</div>
        </Section>
      )}

      {data.rule_findings && data.rule_findings.length > 0 && (
        <Section title="Rule-Based Recommendations">
          <ul>
            {data.rule_findings.map((finding) => (
              <li key={finding.id}>
                <strong>[S{finding.severity}] {finding.title}</strong> — {finding.recommendation}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {data.plan_summary && (
        <Section title="Plan Summary">
          <div className="grid">
            <div>
              <div className="metric-label">Planning</div>
              <div className="metric-value">{formatMs(data.plan_summary.planning_time_ms)}</div>
            </div>
            <div>
              <div className="metric-label">Execution</div>
              <div className="metric-value">{formatMs(data.plan_summary.execution_time_ms)}</div>
            </div>
            <div>
              <div className="metric-label">Total Cost</div>
              <div className="metric-value">{data.plan_summary.total_cost ?? "n/a"}</div>
            </div>
            <div>
              <div className="metric-label">Actual Rows</div>
              <div className="metric-value">{data.plan_summary.actual_rows ?? "n/a"}</div>
            </div>
          </div>
        </Section>
      )}

      {data.preview && (
        <Section title="Result Preview">
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  {data.preview.columns.map((col, idx) => (
                    <th key={idx}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.preview.rows.map((row, rIdx) => (
                  <tr key={rIdx}>
                    {row.map((cell, cIdx) => (
                      <td key={cIdx}>{String(cell)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
    </div>
  );
}

export default function App() {
  const [sql, setSql] = useState(sampleQueries[0]);
  const [messages, setMessages] = useState([]);
  const [autoAnalyze, setAutoAnalyze] = useState(true);
  const [deepAnalyze, setDeepAnalyze] = useState(false);
  const [runPreview, setRunPreview] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [liveResult, setLiveResult] = useState(null);
  const [liveStatus, setLiveStatus] = useState("idle");
  const [liveError, setLiveError] = useState("");
  const [healthStatus, setHealthStatus] = useState("unknown");
  const [healthLatency, setHealthLatency] = useState(null);
  const [liveLatency, setLiveLatency] = useState(null);
  const [manualLatency, setManualLatency] = useState(null);
  const [liveRate, setLiveRate] = useState(0);
  const [manualRate, setManualRate] = useState(0);
  const [ollamaLogs, setOllamaLogs] = useState([]);
  const [ollamaError, setOllamaError] = useState("");
  const [trainingStats, setTrainingStats] = useState(null);
  const [trainingRows, setTrainingRows] = useState([]);
  const [trainingTrends, setTrainingTrends] = useState([]);
  const [trainingError, setTrainingError] = useState("");
  const [feedbackNotes, setFeedbackNotes] = useState({});
  const [filterLabel, setFilterLabel] = useState("all");
  const [filterModel, setFilterModel] = useState("");
  const [filterFrom, setFilterFrom] = useState("");
  const [filterTo, setFilterTo] = useState("");
  const [reviewQueue, setReviewQueue] = useState(false);
  const abortRef = useRef(null);
  const liveTimesRef = useRef([]);
  const manualTimesRef = useRef([]);

  const recordMetric = (ref, setRate, setLatency, latencyMs) => {
    const now = Date.now();
    ref.current = [...ref.current, now].filter((ts) => now - ts < 60000);
    setRate(ref.current.length);
    setLatency(latencyMs);
  };

  useEffect(() => {
    let mounted = true;
    const checkHealth = async () => {
      const start = performance.now();
      try {
        const response = await fetch(`${API_URL}/api/health`);
        const elapsed = performance.now() - start;
        if (!mounted) return;
        if (!response.ok) {
          throw new Error("Health check failed");
        }
        setHealthStatus("ok");
        setHealthLatency(elapsed);
      } catch (err) {
        if (!mounted) return;
        setHealthStatus("down");
        setHealthLatency(null);
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const buildTrainingParams = (extra = {}) => {
    const params = new URLSearchParams();
    const labelValue = reviewQueue ? "unlabeled" : filterLabel;
    if (labelValue && labelValue !== "all") {
      params.set("label", labelValue);
    }
    if (reviewQueue) {
      params.set("unlabeled_first", "true");
    }
    if (filterModel) {
      params.set("model", filterModel);
    }
    if (filterFrom) {
      params.set("date_from", filterFrom);
    }
    if (filterTo) {
      params.set("date_to", filterTo);
    }
    Object.entries(extra).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        params.set(key, String(value));
      }
    });
    return params.toString();
  };

  useEffect(() => {
    let mounted = true;
    const fetchTraining = async () => {
      try {
        const params = buildTrainingParams();
        const [statsRes, listRes] = await Promise.all([
          fetch(`${API_URL}/api/training/stats?${params}`),
          fetch(`${API_URL}/api/training/list?${buildTrainingParams({ limit: 20 })}`),
        ]);
        const statsData = await statsRes.json();
        const listData = await listRes.json();
        if (!statsRes.ok || !listRes.ok) {
          throw new Error("Training fetch failed");
        }
        if (!mounted) return;
        setTrainingStats(statsData);
        setTrainingRows(listData.rows || []);
        setTrainingError("");

        const trendsRes = await fetch(
          `${API_URL}/api/training/trends?${buildTrainingParams({ days: 30 })}`
        );
        const trendsData = await trendsRes.json();
        if (!trendsRes.ok) {
          throw new Error("Trend fetch failed");
        }
        setTrainingTrends(trendsData.points || []);
      } catch (err) {
        if (!mounted) return;
        setTrainingError(err.message || "Training fetch failed");
      }
    };

    fetchTraining();
    const interval = setInterval(fetchTraining, 5000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [filterLabel, filterModel, filterFrom, filterTo, reviewQueue]);

  const updateFeedback = async (id, label) => {
    try {
      const response = await fetch(`${API_URL}/api/training/label`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, label, notes: feedbackNotes[id] || "" }),
      });
      if (!response.ok) {
        throw new Error("Failed to update label");
      }
    } catch (err) {
      setTrainingError(err.message || "Failed to update label");
    }
  };

  const exportTraining = async (format) => {
    try {
      const params = buildTrainingParams({ format, limit: 500 });
      const response = await fetch(`${API_URL}/api/training/export?${params}`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Export failed");
      }
      const blob = new Blob(
        [
          format === "jsonl"
            ? data.rows.map((row) => JSON.stringify(row)).join("\n")
            : toCsv(data.rows),
        ],
        { type: "text/plain" }
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `training_export.${format === "jsonl" ? "jsonl" : "csv"}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setTrainingError(err.message || "Export failed");
    }
  };

  const toCsv = (rows) => {
    if (!rows || rows.length === 0) return "";
    const headers = Object.keys(rows[0]);
    const escape = (value) =>
      `"${String(value ?? "").replace(/"/g, '""')}"`;
    const lines = [headers.join(",")];
    for (const row of rows) {
      lines.push(headers.map((h) => escape(row[h])).join(","));
    }
    return lines.join("\n");
  };
  useEffect(() => {
    let mounted = true;
    const fetchLogs = async () => {
      try {
        const response = await fetch(`${API_URL}/api/ollama/logs?limit=160`);
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Log fetch failed");
        }
        if (!mounted) return;
        setOllamaLogs(data.logs || []);
        setOllamaError("");
      } catch (err) {
        if (!mounted) return;
        setOllamaError(err.message || "Log fetch failed");
      }
    };

    fetchLogs();
    const interval = setInterval(fetchLogs, 2500);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!autoAnalyze) return undefined;
    if (!sql.trim()) {
      setLiveResult(null);
      setLiveStatus("idle");
      return undefined;
    }

    setLiveStatus("analyzing");
    setLiveError("");

    if (abortRef.current) {
      abortRef.current.abort();
    }

    const controller = new AbortController();
    abortRef.current = controller;

    const timeout = setTimeout(async () => {
      const started = performance.now();
      try {
        const response = await fetch(`${API_URL}/api/analyze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            sql,
            run_analyze: deepAnalyze,
            run_preview: false,
            analysis_mode: "live",
          }),
          signal: controller.signal,
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Live analysis failed");
        }

        setLiveResult(data);
        setLiveStatus("ready");
        recordMetric(liveTimesRef, setLiveRate, setLiveLatency, performance.now() - started);
      } catch (err) {
        if (err.name === "AbortError") return;
        setLiveError(err.message || "Live analysis failed");
        setLiveStatus("error");
      }
    }, 700);

    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [sql, autoAnalyze, deepAnalyze]);

  const handleRun = async () => {
    if (!sql.trim()) return;
    setLoading(true);
    setError("");

    const userMessage = { role: "user", sql };
    setMessages((prev) => [...prev, userMessage]);

    const started = performance.now();
    try {
      const response = await fetch(`${API_URL}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sql,
          run_analyze: deepAnalyze,
          run_preview: runPreview,
          analysis_mode: "manual",
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Request failed");
      }

      setMessages((prev) => [...prev, { role: "assistant", data }]);
      recordMetric(manualTimesRef, setManualRate, setManualLatency, performance.now() - started);
    } catch (err) {
      setError(err.message || "Unexpected error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="top-bar">
        <div className="brand">QuerySense</div>
        <div className="subtitle">Local, explainable query optimization MVP</div>
      </header>

      <main className="main">
        <div className="layout">
          <aside className="left-rail">
            <div className="panel">
              <div className="panel-title">Agent Health</div>
              <StatusPill
                status={healthStatus === "ok" ? "ok" : healthStatus === "down" ? "down" : "warn"}
                label={
                  healthStatus === "ok"
                    ? "API Healthy"
                    : healthStatus === "down"
                    ? "API Down"
                    : "Checking..."
                }
              />
              <div className="panel-grid">
                <MetricCard label="Ping latency" value={formatMs(healthLatency)} />
                <MetricCard label="Live status" value={liveStatus === "ready" ? "Active" : "Idle"} />
              </div>
            </div>

            <div className="panel">
              <div className="panel-title">Response Metrics</div>
              <div className="panel-grid">
                <MetricCard label="Live latency" value={formatMs(liveLatency)} />
                <MetricCard label="Live rate" value={formatRate(liveRate)} />
                <MetricCard label="Manual latency" value={formatMs(manualLatency)} />
                <MetricCard label="Manual rate" value={formatRate(manualRate)} />
              </div>
              <div className="panel-note">Rates are calculated over the last 60 seconds.</div>
            </div>

            <div className="panel accent">
              <div className="panel-title">Agent Tips</div>
              <ul className="tips">
                <li>Prefer filters on indexed columns.</li>
                <li>Use LIMIT with ORDER BY when exploring.</li>
                <li>Deep analysis executes the query.</li>
              </ul>
            </div>
          </aside>

          <div className="main-column">
            <section className="composer">
              <div className="composer-header">
                <div className="label">SQL Editor</div>
                <div className="toggles">
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={autoAnalyze}
                      onChange={(e) => setAutoAnalyze(e.target.checked)}
                    />
                    Live agent
                  </label>
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={deepAnalyze}
                      onChange={(e) => setDeepAnalyze(e.target.checked)}
                    />
                    Deep analysis (EXPLAIN ANALYZE)
                  </label>
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={runPreview}
                      onChange={(e) => setRunPreview(e.target.checked)}
                    />
                    Preview rows
                  </label>
                </div>
              </div>
              <div className="hint">
                Deep analysis runs EXPLAIN ANALYZE and executes the query. Use with care on huge data.
              </div>

          <textarea
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            spellCheck={false}
            rows={12}
          />

              <div className="composer-actions">
                <div className="chips">
                  {sampleQueries.map((query, index) => (
                    <button
                      key={index}
                      className="chip"
                      type="button"
                      onClick={() => setSql(query)}
                    >
                      Sample {index + 1}
                    </button>
                  ))}
                </div>
                <button className="run" type="button" onClick={handleRun} disabled={loading}>
                  {loading ? "Analyzing..." : "Run Manual Analysis"}
                </button>
              </div>
              {error && <div className="error">{error}</div>}
            </section>

            <section className="chat">
              {messages.length === 0 && (
                <div className="empty">Run a query to see analysis results.</div>
              )}

              {messages.map((message, index) => {
                if (message.role === "user") {
                  return (
                    <div key={index} className="message user">
                      <div className="message-title">You</div>
                      <pre>{message.sql}</pre>
                    </div>
                  );
                }

                const data = message.data;
                return (
                  <div key={index} className="message assistant">
                    <div className="message-title">SQL Analyst</div>
                    <AnalysisPanel data={data} />
                  </div>
                );
              })}
            </section>

            <section className="training-dashboard">
              <div className="panel">
                <div className="panel-title">Training & Evaluation</div>
                {trainingError && <div className="error">{trainingError}</div>}
                <div className="training-filters">
                  <select
                    value={filterLabel}
                    onChange={(e) => setFilterLabel(e.target.value)}
                  >
                    <option value="all">All labels</option>
                    <option value="good">Good</option>
                    <option value="bad">Bad</option>
                    <option value="needs_review">Needs review</option>
                    <option value="unlabeled">Unlabeled</option>
                  </select>
                  <input
                    placeholder="Model name"
                    value={filterModel}
                    onChange={(e) => setFilterModel(e.target.value)}
                  />
                  <input
                    type="date"
                    value={filterFrom}
                    onChange={(e) => setFilterFrom(e.target.value)}
                  />
                  <input
                    type="date"
                    value={filterTo}
                    onChange={(e) => setFilterTo(e.target.value)}
                  />
                  <button
                    className={`ghost ${reviewQueue ? "active" : ""}`}
                    type="button"
                    onClick={() => setReviewQueue((prev) => !prev)}
                  >
                    Review queue
                  </button>
                  <button
                    className="ghost"
                    type="button"
                    onClick={() => {
                      setFilterLabel("all");
                      setFilterModel("");
                      setFilterFrom("");
                      setFilterTo("");
                      setReviewQueue(false);
                    }}
                  >
                    Reset
                  </button>
                </div>
                {trainingStats && (
                  <div className="panel-grid">
                    <MetricCard label="Samples" value={trainingStats.total ?? 0} />
                    <MetricCard label="Avg score" value={trainingStats.avg_score ?? "n/a"} />
                    <MetricCard
                      label="Good labels"
                      value={trainingStats.by_label?.good ?? 0}
                    />
                    <MetricCard
                      label="Bad labels"
                      value={trainingStats.by_label?.bad ?? 0}
                    />
                    <MetricCard
                      label="Avg score (good)"
                      value={trainingStats.avg_score_good ?? "n/a"}
                    />
                    <MetricCard
                      label="Avg score (bad)"
                      value={trainingStats.avg_score_bad ?? "n/a"}
                    />
                  </div>
                )}
                <div className="trend-block">
                  <div className="trend-title">LLM Quality Trend (30 days)</div>
                  <TrendChart data={trainingTrends} />
                </div>
                <div className="panel-actions">
                  <button className="ghost" type="button" onClick={() => exportTraining("jsonl")}>
                    Export JSONL
                  </button>
                  <button className="ghost" type="button" onClick={() => exportTraining("csv")}>
                    Export CSV
                  </button>
                </div>
                <div className="training-table">
                  <div className="training-header">
                    <span>Created</span>
                    <span>Model</span>
                    <span>Score</span>
                    <span>Label</span>
                    <span>Actions</span>
                  </div>
                  {trainingRows.map((row) => (
                    <div key={row.id} className="training-row">
                      <span>{row.created_at ? row.created_at.slice(0, 19).replace("T", " ") : ""}</span>
                      <span>{row.model_used || "n/a"}</span>
                      <span>{row.score ?? "n/a"} ({row.grade || "-"})</span>
                      <span>{row.feedback_label || "unlabeled"}</span>
                      <span className="tag-actions">
                        <input
                          className="tag-note"
                          placeholder="note"
                          value={feedbackNotes[row.id] || ""}
                          onChange={(e) =>
                            setFeedbackNotes((prev) => ({ ...prev, [row.id]: e.target.value }))
                          }
                        />
                        <button className="ghost" onClick={() => updateFeedback(row.id, "good")}>
                          Good
                        </button>
                        <button className="ghost" onClick={() => updateFeedback(row.id, "bad")}>
                          Bad
                        </button>
                        <button className="ghost" onClick={() => updateFeedback(row.id, "needs_review")}>
                          Needs review
                        </button>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <section className="ollama-logs">
              <div className="panel">
                <div className="panel-title">Ollama Live Logs</div>
                {ollamaError && <div className="error">{ollamaError}</div>}
                <div className="logs">
                  {ollamaLogs.length === 0 ? (
                    <div className="note">No LLM activity yet.</div>
                  ) : (
                    <pre>
                      {ollamaLogs
                        .map(
                          (entry) =>
                            `[${entry.ts}] ${entry.level} ${entry.message} ${entry.meta && Object.keys(entry.meta).length > 0 ? JSON.stringify(entry.meta) : ""}`
                        )
                        .join("\n")}
                    </pre>
                  )}
                </div>
              </div>
            </section>
          </div>

          <aside className="right-rail">
            <div className="panel">
              <div className="panel-title">Live Agent</div>
              <div className="note">
                Status:{" "}
                {liveStatus === "idle"
                  ? "Idle"
                  : liveStatus === "analyzing"
                  ? "Analyzing..."
                  : liveStatus === "error"
                  ? "Error"
                  : "Ready"}
              </div>
              {liveError && <div className="error">{liveError}</div>}
              {liveResult ? (
                <AnalysisPanel data={liveResult} />
              ) : (
                <div className="note">Start typing to trigger live optimization checks.</div>
              )}
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
