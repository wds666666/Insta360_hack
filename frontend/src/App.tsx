import { useEffect, useRef, useState } from "react";
import { continueMesh, createRun, getRun, listRuns } from "./api";
import { GlbViewer } from "./components/GlbViewer";
import { ImagePanel } from "./components/ImagePanel";
import { PromptForm } from "./components/PromptForm";
import { StageList } from "./components/StageList";
import { TaskList } from "./components/TaskList";
import { formatDuration, meshSeconds, stepSeconds, useNow } from "./meshTime";
import type { RunRecord, RunSummary } from "./types";

const RUN_KEY = "chujian-run-id";

function runFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("run");
}

function rememberedRun(): string | null {
  return runFromUrl() || sessionStorage.getItem(RUN_KEY);
}

function writeRunUrl(runId: string | null) {
  const url = new URL(window.location.href);
  if (runId) {
    url.searchParams.set("run", runId);
    sessionStorage.setItem(RUN_KEY, runId);
  } else {
    url.searchParams.delete("run");
    sessionStorage.removeItem(RUN_KEY);
  }
  window.history.replaceState(null, "", url);
}

export function App() {
  const [runId, setRunId] = useState<string | null>(rememberedRun);
  const restored = useRef(Boolean(rememberedRun()));
  const [run, setRun] = useState<RunRecord | null>(null);
  const [tasks, setTasks] = useState<RunSummary[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [pollEpoch, setPollEpoch] = useState(0);

  const running = run?.status === "pending" || run?.status === "running";
  const optimizeRunning = run?.nodes.some((node) => node.name === "optimize_image" && node.status === "running") ?? false;
  const meshRunning = run?.nodes.some((node) => node.name === "poll_mesh" && node.status === "running") ?? false;
  const now = useNow(optimizeRunning || meshRunning);
  const optimize = stepSeconds(run, "optimize_image", now);
  const mesh = meshSeconds(run, now);
  const meshMeter = meshRunning
    ? mesh == null
      ? "刚刚开始"
      : `已进行 ${formatDuration(mesh)}`
    : mesh == null
      ? null
      : `用时 ${formatDuration(mesh)}`;
  const optimizeNote = optimizeRunning
    ? `正在整理空间，已进行 ${optimize == null ? "刚刚开始" : formatDuration(optimize)}`
    : "去掉人物、杂物和文字，留下可触摸的墙面与家具";
  const busy = tasks.some((task) => task.status === "pending" || task.status === "running");

  useEffect(() => {
    if (!runId) {
      return;
    }
    let stop = false;
    let timer = 0;
    const tick = async () => {
      try {
        const next = await getRun(runId);
        if (stop) {
          return;
        }
        setRun(next);
        setSubmitting(false);
        if (next.status === "pending" || next.status === "running") {
          timer = window.setTimeout(tick, 2000);
        }
      } catch (error) {
        if (!stop) {
          setNotice(error instanceof Error ? error.message : "查询失败");
        }
      }
    };
    void tick();
    return () => {
      stop = true;
      window.clearTimeout(timer);
    };
  }, [runId, pollEpoch]);

  useEffect(() => {
    let stop = false;
    const load = async () => {
      try {
        const next = await listRuns();
        if (!stop) {
          setTasks(next);
          setListError(null);
          if (!restored.current) {
            restored.current = true;
            const saved = rememberedRun();
            const active = next.find(
              (task) => task.status === "pending" || task.status === "running" || task.status === "awaiting_mesh",
            );
            const known = saved && next.some((task) => task.run_id === saved) ? saved : null;
            const resume = known || active?.run_id || null;
            if (resume) {
              setRunId(resume);
              writeRunUrl(resume);
            }
          }
        }
      } catch (error) {
        if (!stop) {
          setListError(error instanceof Error ? error.message : "任务列表读取失败");
        }
      }
    };
    void load();
    const timer = window.setInterval(load, 4000);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    return () => {
      if (preview) {
        URL.revokeObjectURL(preview);
      }
    };
  }, [preview]);

  return (
    <div className="page">
      <header className="mast">
        <h1 className="logo">
          <img src="/logo.png" alt="触见，给视障者的空间地图" />
        </h1>
        <div className="mast-copy">
          <p className="lede">
            我们做了一个将视觉空间转化为触觉语言的 AI 空间地图，给视障者使用，解决他们无法通过视觉建立空间认知的问题。
          </p>
          <p className="slogan">真正做到「人人平等」，让残障人士也可以更好的理解世界。</p>
        </div>
      </header>
      <div className="layout">
        <aside>
          <TaskList
            tasks={tasks}
            selectedId={runId}
            error={listError}
            onSelect={(id) => {
              if (preview) {
                URL.revokeObjectURL(preview);
                setPreview(null);
              }
              setNotice(null);
              setRun(null);
              setRunId(id);
              writeRunUrl(id);
            }}
            onCreate={() => {
              if (preview) {
                URL.revokeObjectURL(preview);
                setPreview(null);
              }
              setNotice(null);
              setRun(null);
              setRunId(null);
              writeRunUrl(null);
            }}
          />
          <PromptForm
            disabled={running || busy || submitting}
            onImage={(file) => {
              setPreview((current) => {
                if (current) {
                  URL.revokeObjectURL(current);
                }
                return file ? URL.createObjectURL(file) : null;
              });
            }}
            onSubmit={(prompt, image, mode) => {
              setNotice(null);
              setRun(null);
              setSubmitting(true);
              void createRun(prompt, image, mode)
                .then((created) => {
                  setRunId(created.run_id);
                  writeRunUrl(created.run_id);
                  void listRuns()
                    .then(setTasks)
                    .catch(() => undefined);
                })
                .catch((error: unknown) => {
                  setSubmitting(false);
                  setNotice(error instanceof Error ? error.message : "创建失败");
                });
            }}
          />
          {notice ? (
            <p className="error" role="alert">
              {notice}
            </p>
          ) : null}
          <StageList run={run} />
        </aside>
        <main>
          <div className="images">
            <ImagePanel
              title="全景原图"
              note="拍摄到的视觉空间"
              src={preview ?? run?.outputs.reference_image ?? null}
              empty="放入全景后，原始空间显示在这里"
            />
            <ImagePanel
              title="空间结构"
              note={optimizeNote}
              src={run?.outputs.optimized_image ?? null}
              empty="优化完成后，空间结构显示在这里"
            />
          </div>
          <GlbViewer
            src={run?.outputs.model_glb ?? null}
            meter={meshMeter}
            flowing={meshRunning}
            onContinue={
              run?.status === "awaiting_mesh" && runId
                ? () => {
                    setNotice(null);
                    setSubmitting(true);
                    void continueMesh(runId)
                      .then(() => {
                        setRun((current) => (current ? { ...current, status: "running" } : current));
                        setPollEpoch((value) => value + 1);
                      })
                      .catch((error: unknown) => {
                        setSubmitting(false);
                        setNotice(error instanceof Error ? error.message : "没能开始生成模型");
                      });
                  }
                : null
            }
          />
        </main>
      </div>
    </div>
  );
}
