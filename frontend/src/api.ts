import type { RunMode, RunRecord, RunSummary } from "./types";

export async function listRuns(): Promise<RunSummary[]> {
  const response = await fetch("/api/v1/runs", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const body = (await response.json()) as { runs: RunSummary[] };
  return body.runs;
}

export async function createRun(prompt: string, image: File, mode: RunMode): Promise<{ run_id: string }> {
  const body = new FormData();
  body.set("workflow_id", "img-to-3d");
  body.set("prompt", prompt);
  body.set("image", image);
  body.set("mode", mode);
  const response = await fetch("/api/v1/runs", { method: "POST", body });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function continueMesh(runId: string): Promise<void> {
  const response = await fetch(`/api/v1/runs/${runId}/mesh`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
}

export async function getRun(runId: string): Promise<RunRecord> {
  const response = await fetch(`/api/v1/runs/${runId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    /* 响应不是 JSON */
  }
  return `请求失败（${response.status}）`;
}
