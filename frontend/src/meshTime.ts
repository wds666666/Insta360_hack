import { useEffect, useState } from "react";
import type { RunRecord } from "./types";

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  if (minutes === 0) {
    return `${rest} 秒`;
  }
  return `${minutes} 分 ${rest.toString().padStart(2, "0")} 秒`;
}

export function secondsSince(startedAt: string | undefined, now: number): number | null {
  if (!startedAt) {
    return null;
  }
  const started = Date.parse(startedAt);
  if (Number.isNaN(started)) {
    return null;
  }
  return Math.max(0, Math.floor((now - started) / 1000));
}

const STARTED_AT = {
  optimize_image: "optimize_image_started_at",
  poll_mesh: "poll_mesh_started_at",
} as const;

const ELAPSED = {
  optimize_image: "optimize_image_elapsed_seconds",
  poll_mesh: "poll_mesh_elapsed_seconds",
} as const;

export function stepSeconds(run: RunRecord | null, nodeName: keyof typeof STARTED_AT, now: number): number | null {
  const node = run?.nodes.find((item) => item.name === nodeName);
  if (!node || node.status === "pending" || node.status === "skipped") {
    return null;
  }
  if (node.status === "running") {
    return secondsSince(run?.artifacts[STARTED_AT[nodeName]], now);
  }
  const finished = run?.artifacts[ELAPSED[nodeName]];
  return typeof finished === "number" ? finished : null;
}

export function meshSeconds(run: RunRecord | null, now: number): number | null {
  return stepSeconds(run, "poll_mesh", now);
}

export function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) {
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}
