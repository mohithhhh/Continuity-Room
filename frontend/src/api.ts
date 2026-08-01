export type FlagType = "character" | "prop" | "location" | "timeline";
export type Severity = "low" | "medium" | "high" | "critical";

export interface ContinuityFlagDraft {
  event_id_a: string;
  event_id_b: string;
  flag_type: FlagType;
  severity: Severity;
  explanation: string;
}

export interface ContinuityReport {
  script_id: string;
  flags: ContinuityFlagDraft[];
}

export interface PipelineStageResult {
  stage: string;
  status: "complete" | "failed" | string;
  detail: string;
}

export interface PipelineResult {
  script_id: string;
  stages: PipelineStageResult[];
  events_written: number;
  report: ContinuityReport | null;
  studio_head_summary: string;
}

export async function getConfig(): Promise<{ grafana_dashboard_url: string | null }> {
  const res = await fetch("/api/config");
  if (!res.ok) return { grafana_dashboard_url: null };
  return res.json();
}

export async function runPipeline(
  scriptId: string,
  rawText: string,
): Promise<PipelineResult> {
  const res = await fetch("/api/pipeline/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ script_id: scriptId, raw_text: rawText }),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Pipeline run failed (${res.status}): ${body}`);
  }
  return res.json();
}
