import type { CaptureRecord, RunMode, RunRecord, RunSource, RunSummary } from "./types";

export async function listRuns(): Promise<RunSummary[]> {
  const response = await fetch("/api/v1/runs", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const body = (await response.json()) as { runs: RunSummary[] };
  return body.runs;
}

function accessHeaders(password: string, extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  headers.set("X-Access-Password", password);
  return headers;
}

export async function createRun(
  prompt: string,
  source: RunSource,
  mode: RunMode,
  password: string,
): Promise<{ run_id: string }> {
  const body = new FormData();
  body.set("workflow_id", "img-to-3d");
  body.set("prompt", prompt);
  if (source.kind === "upload") {
    for (const image of source.images) {
      body.append("image", image);
    }
  } else {
    body.set("capture_id", source.captureId);
    body.set("capture_views", JSON.stringify(source.selectedKeys));
  }
  body.set("mode", mode);
  const response = await fetch("/api/v1/runs", { method: "POST", body, headers: accessHeaders(password) });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function createCapture(): Promise<{ capture_id: string; status: string }> {
  const response = await fetch("/api/v1/camera/captures", { method: "POST" });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function getCapture(captureId: string): Promise<CaptureRecord> {
  const response = await fetch(`/api/v1/camera/captures/${encodeURIComponent(captureId)}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function continueImage(runId: string, prompt: string, password: string): Promise<void> {
  const response = await fetch(`/api/v1/runs/${runId}/image`, {
    method: "POST",
    headers: accessHeaders(password, { "Content-Type": "application/json" }),
    body: JSON.stringify({ prompt }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
}

export async function continueMesh(runId: string, password: string): Promise<void> {
  const response = await fetch(`/api/v1/runs/${runId}/mesh`, {
    method: "POST",
    headers: accessHeaders(password),
  });
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
    if (body.detail && typeof body.detail.message === "string") {
      return body.detail.message;
    }
  } catch {
    /* 响应不是 JSON */
  }
  return `请求失败（${response.status}）`;
}
