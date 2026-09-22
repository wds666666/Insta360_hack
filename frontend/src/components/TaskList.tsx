import type { RunSummary } from "../types";

const STATUS_LABEL: Record<string, string> = {
  pending: "等待",
  running: "进行中",
  succeeded: "完成",
  awaiting_mesh: "等你确认",
  failed: "失败",
};

type Props = {
  tasks: RunSummary[];
  selectedId: string | null;
  error: string | null;
  onSelect: (runId: string) => void;
  onCreate: () => void;
};

export function TaskList({ tasks, selectedId, error, onSelect, onCreate }: Props) {
  return (
    <section className="tasks" aria-label="已有任务">
      <div className="tasks-head">
        <h2>已有任务</h2>
        <button type="button" className="task-new" onClick={onCreate}>
          新任务
        </button>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {tasks.length === 0 ? <p className="muted">生成之后，可以从这里回到之前的空间地图。</p> : null}
      <ul className="task-list">
        {tasks.map((task) => {
          const status = task.status === "running" && task.current_label ? task.current_label : STATUS_LABEL[task.status] ?? task.status;
          return (
            <li key={task.run_id}>
              <button
                type="button"
                aria-current={task.run_id === selectedId ? "true" : undefined}
                onClick={() => onSelect(task.run_id)}
              >
                {task.reference_image ? (
                  <img src={task.reference_image} alt="" />
                ) : (
                  <span className="task-thumb" aria-hidden="true" />
                )}
                <span className="task-copy">
                  <strong>{task.prompt || "未命名空间"}</strong>
                  <span className="task-meta">
                    {formatWhen(task.created_at)} · {status}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function formatWhen(iso: string | null): string {
  if (!iso) {
    return "较早的任务";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "较早的任务";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
