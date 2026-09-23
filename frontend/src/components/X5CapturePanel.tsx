import { useEffect, useRef, useState } from "react";
import { createCapture, getCapture } from "../api";
import type { CaptureCandidate, CaptureRecord } from "../types";

const DEFAULT_KEYS = new Set(["panorama", "little_planet", "front", "right", "back", "left", "down"]);
const SUCCESS_STATUSES = new Set(["succeeded", "success", "completed", "complete", "ready"]);
const FAILED_STATUSES = new Set(["failed", "error", "cancelled", "canceled"]);

type CaptureSelection = {
  captureId: string;
  candidates: CaptureCandidate[];
  selectedKeys: string[];
};

type Props = {
  disabled: boolean;
  onChange: (selection: CaptureSelection | null) => void;
};

function normalizeCandidates(record: CaptureRecord): CaptureCandidate[] {
  const raw = record.candidates;
  if (!raw) {
    return [];
  }
  if (Array.isArray(raw)) {
    return raw
      .filter((item) => item && item.key && item.url)
      .slice(0, 8)
      .map((item) => ({
        key: item.key,
        label: item.label || item.key,
        url: item.url,
        default_selected: DEFAULT_KEYS.has(item.key.replace(/^view_/, "")),
      }));
  }
  return Object.entries(raw)
    .map(([key, value]) => {
      if (typeof value === "string") {
        return { key, label: key, url: value, default_selected: DEFAULT_KEYS.has(key.replace(/^view_/, "")) };
      }
      const candidateKey = value.key || key;
      return {
        key: candidateKey,
        label: value.label || key,
        url: value.url || "",
        default_selected: DEFAULT_KEYS.has(candidateKey.replace(/^view_/, "")),
      };
    })
    .filter((item) => item.url)
    .slice(0, 8);
}

function captureError(record: CaptureRecord): string {
  if (typeof record.error === "string") {
    return record.error;
  }
  return record.error?.message || "X5 拍摄失败，请重试";
}

export function X5CapturePanel({ disabled, onChange }: Props) {
  const [captureId, setCaptureId] = useState<string | null>(null);
  const [status, setStatus] = useState("idle");
  const [stepLabel, setStepLabel] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<CaptureCandidate[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const requestEpoch = useRef(0);
  const normalizedStatus = status.toLowerCase();

  useEffect(() => {
    if (!captureId || candidates.length || (FAILED_STATUSES.has(normalizedStatus) && error)) {
      return;
    }
    let stopped = false;
    let timer = 0;
    const epoch = requestEpoch.current;
    const poll = async () => {
      try {
        const record = await getCapture(captureId);
        if (stopped || epoch !== requestEpoch.current) {
          return;
        }
        const nextStatus = record.status.toLowerCase();
        setStatus(nextStatus);
        setStepLabel(record.step_label ?? null);
        if (SUCCESS_STATUSES.has(nextStatus)) {
          const nextCandidates = normalizeCandidates(record);
          if (!nextCandidates.length) {
            setStatus("failed");
            setError("拍摄已完成，但没有可用的候选图片");
            return;
          }
          const defaults = nextCandidates
            .filter((item) => item.default_selected)
            .map((item) => item.key)
            .slice(0, 8);
          const nextSelected = defaults.length ? defaults : [nextCandidates[0].key];
          setCandidates(nextCandidates);
          setSelectedKeys(nextSelected);
          onChange({ captureId, candidates: nextCandidates, selectedKeys: nextSelected });
          return;
        }
        if (FAILED_STATUSES.has(nextStatus)) {
          setError(captureError(record));
          onChange(null);
          return;
        }
        timer = window.setTimeout(poll, 1500);
      } catch (reason) {
        if (!stopped && epoch === requestEpoch.current) {
          setStatus("failed");
          setError(reason instanceof Error ? reason.message : "无法查询 X5 拍摄状态");
          onChange(null);
        }
      }
    };
    void poll();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [candidates.length, captureId, error, normalizedStatus, onChange]);

  const beginCapture = async () => {
    requestEpoch.current += 1;
    setCaptureId(null);
    setCandidates([]);
    setSelectedKeys([]);
    setError(null);
    setStepLabel("正在连接 X5");
    setStatus("starting");
    onChange(null);
    try {
      const created = await createCapture();
      setCaptureId(created.capture_id);
      setStatus(created.status);
    } catch (reason) {
      setStatus("failed");
      setError(reason instanceof Error ? reason.message : "无法启动 X5 拍摄");
    }
  };

  const updateSelection = (next: string[]) => {
    if (!captureId || next.length > 8) {
      return;
    }
    setSelectedKeys(next);
    if (!next.length) {
      setError("提交前至少选择一张图片");
      onChange(null);
      return;
    }
    setError(null);
    onChange({ captureId, candidates, selectedKeys: next });
  };

  const busy =
    normalizedStatus === "starting" ||
    (captureId !== null && !candidates.length && !FAILED_STATUSES.has(normalizedStatus));

  return (
    <section className="x5-capture" aria-live="polite">
      {!candidates.length ? (
        <div className="capture-start">
          <button className="file-button" type="button" disabled={disabled || busy} onClick={() => void beginCapture()}>
            {busy ? "X5 拍摄中" : error ? "重新拍摄" : "开始 X5 拍摄"}
          </button>
          <span>{busy ? stepLabel || "正在处理拍摄结果" : "相机将拍摄并生成 8 个可选视角"}</span>
        </div>
      ) : (
        <>
          <div className="capture-toolbar">
            <span>已选 {selectedKeys.length} / {candidates.length} 张</span>
            <div>
              <button type="button" disabled={disabled || selectedKeys.length === candidates.length} onClick={() => updateSelection(candidates.map((item) => item.key))}>
                全选
              </button>
              <button type="button" disabled={disabled || selectedKeys.length === 0} onClick={() => updateSelection([])}>
                取消全选
              </button>
              <button type="button" disabled={disabled} onClick={() => void beginCapture()}>
                重新拍摄
              </button>
            </div>
          </div>
          <div className="capture-grid">
            {candidates.map((candidate) => {
              const selected = selectedKeys.includes(candidate.key);
              return (
                <label className={selected ? "capture-card is-selected" : "capture-card"} key={candidate.key}>
                  <input
                    type="checkbox"
                    checked={selected}
                    disabled={disabled}
                    onChange={() =>
                      updateSelection(
                        selected ? selectedKeys.filter((key) => key !== candidate.key) : [...selectedKeys, candidate.key],
                      )
                    }
                  />
                  <img src={candidate.url} alt={candidate.label} loading="lazy" />
                  <span>{candidate.label}</span>
                </label>
              );
            })}
          </div>
          <p className="capture-success">拍摄完成。恢复互联网连接后，再提交给 DeepSeek 生成触觉地图。</p>
        </>
      )}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
