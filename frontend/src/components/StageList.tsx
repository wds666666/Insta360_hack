import { formatDuration, stepSeconds, useNow } from "../meshTime";
import type { RunRecord } from "../types";

const STATUS_LABEL: Record<string, string> = {
  pending: "等待",
  running: "进行中",
  succeeded: "完成",
  failed: "失败",
  skipped: "跳过",
};

const STATUS_MARK: Record<string, string> = {
  pending: "○",
  running: "●",
  succeeded: "✓",
  failed: "!",
  skipped: "–",
};

type Props = {
  run: RunRecord | null;
};

export function StageList({ run }: Props) {
  const nodes = run?.nodes ?? [];
  const ticking = nodes.some(
    (node) => (node.name === "optimize_image" || node.name === "poll_mesh") && node.status === "running",
  );
  const now = useNow(ticking);
  const optimize = stepSeconds(run, "optimize_image", now);
  const optimizeRunning = nodes.some((node) => node.name === "optimize_image" && node.status === "running");
  const mesh = stepSeconds(run, "poll_mesh", now);
  const meshRunning = nodes.some((node) => node.name === "poll_mesh" && node.status === "running");
  const vendor =
    run?.artifacts.lux3d_stage && run.artifacts.lux3d_status_label
      ? `${run.artifacts.lux3d_stage} · ${run.artifacts.lux3d_status_label}`
      : null;

  return (
    <section className="stages" aria-label="生成进度">
      <h2>从看见到可触摸</h2>
      {nodes.length === 0 ? <p className="muted">放入全景后，每一步都会显示：保存空间、整理结构、生成可触摸的模型。</p> : null}
      <ol>
        {nodes.map((node) => (
          <li key={node.name} data-status={node.status} aria-current={node.name === run?.current_node ? "step" : undefined}>
            <span className="stage-label">
              {node.label}
              {node.name === "optimize_image" && optimize != null ? (
                <span className="stage-time">
                  {optimizeRunning ? `已进行 ${formatDuration(optimize)}` : `用时 ${formatDuration(optimize)}`}
                </span>
              ) : null}
              {node.name === "poll_mesh" && mesh != null ? (
                <span className="stage-time">{meshRunning ? `已进行 ${formatDuration(mesh)}` : `用时 ${formatDuration(mesh)}`}</span>
              ) : null}
            </span>
            <span className="stage-status">
              <span aria-hidden="true">{STATUS_MARK[node.status] ?? "·"}</span>
              {STATUS_LABEL[node.status] ?? node.status}
            </span>
          </li>
        ))}
      </ol>
      {vendor ? <p className="vendor">{vendor}</p> : null}
      {run?.error ? (
        <p className="error" role="alert">
          {run.error.message}
        </p>
      ) : null}
    </section>
  );
}
