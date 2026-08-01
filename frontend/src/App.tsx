import { useEffect, useRef, useState } from "react";

import { getConfig, PipelineResult, runPipeline } from "./api";

const STAGES = [
  {
    key: "technical_producer",
    name: "Technical Producer",
    running: "Extracting structured events with Gemini and writing to ClickHouse…",
  },
  {
    key: "director",
    name: "Director",
    running: "Querying ClickHouse (read-only, via MCP) for contradictions…",
  },
  {
    key: "studio_head",
    name: "Studio Head",
    running: "Applying governance, writing the audit log, publishing to Grafana…",
  },
] as const;

const SAMPLE_SCRIPT_ID = "the-last-ledger";

export default function App() {
  const [scriptId, setScriptId] = useState(SAMPLE_SCRIPT_ID);
  const [rawText, setRawText] = useState("");
  const [running, setRunning] = useState(false);
  const [revealCount, setRevealCount] = useState(0);
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [grafanaUrl, setGrafanaUrl] = useState<string | null>(null);

  useEffect(() => {
    getConfig().then((c) => setGrafanaUrl(c.grafana_dashboard_url));
  }, []);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setRawText(text);
    if (!scriptId || scriptId === SAMPLE_SCRIPT_ID) {
      setScriptId(file.name.replace(/\.[^/.]+$/, ""));
    }
  }

  async function handleRun() {
    if (!rawText.trim() || running) return;
    setRunning(true);
    setError(null);
    setResult(null);
    setRevealCount(0);

    try {
      const pipelineResult = await runPipeline(scriptId, rawText);
      for (let i = 1; i <= pipelineResult.stages.length; i++) {
        await new Promise((r) => setTimeout(r, 450));
        setRevealCount(i);
      }
      setResult(pipelineResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="page">
      <header>
        <h1>Continuity Room</h1>
        <p className="tagline">
          Multi-agent script supervisor — catches character, prop, and
          timeline contradictions before they hit set.
        </p>
      </header>

      <div className="panel">
        <div className="field">
          <label htmlFor="script-id">Script ID</label>
          <input
            id="script-id"
            type="text"
            value={scriptId}
            onChange={(e) => setScriptId(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="raw-text">Script excerpt</label>
          <textarea
            id="raw-text"
            placeholder="Paste one or more scenes here, or upload a file below..."
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
          />
        </div>

        <div className="row">
          <button onClick={handleRun} disabled={running || !rawText.trim()}>
            {running ? "Running pipeline…" : "Run pipeline"}
          </button>
          <button
            className="secondary"
            onClick={() => fileInputRef.current?.click()}
            disabled={running}
          >
            Upload file
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".md,.txt"
            style={{ display: "none" }}
            onChange={handleFile}
          />
          {grafanaUrl && (
            <a
              className="grafana-link"
              href={grafanaUrl}
              target="_blank"
              rel="noreferrer"
            >
              Open live Grafana dashboard ↗
            </a>
          )}
        </div>

        {error && <p className="error">{error}</p>}
      </div>

      {(running || result) && (
        <div className="panel">
          <div className="stages">
            {STAGES.map((stage, i) => {
              const revealed = i < revealCount;
              const stageResult = revealed ? result?.stages[i] : undefined;
              const status = stageResult?.status;
              const isActive = running && i === revealCount;
              const cls = status === "failed" ? "failed" : status === "complete" ? "done" : isActive ? "active" : "";
              const icon = status === "failed" ? "✖" : status === "complete" ? "✓" : isActive ? "●" : "○";
              return (
                <div key={stage.key} className={`stage ${cls}`}>
                  <span className="icon">{icon}</span>
                  <div>
                    <div className="name">{stage.name}</div>
                    <div className="detail">
                      {stageResult?.detail ?? (isActive ? stage.running : "Pending")}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {result && (
        <div className="panel">
          <p className="muted">
            {result.events_written} event(s) written ·{" "}
            {result.report?.flags.length ?? 0} continuity flag(s) found for
            script "{result.script_id}"
          </p>
          {result.report && result.report.flags.length > 0 && (
            <div className="flag-list">
              {result.report.flags.map((flag, i) => (
                <div className="flag" key={i}>
                  <span className={`badge ${flag.severity}`}>{flag.severity}</span>
                  <span className="badge low">{flag.flag_type}</span>
                  <p style={{ margin: "0.5rem 0 0" }}>{flag.explanation}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
