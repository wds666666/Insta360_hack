export type NodeStatus = "pending" | "running" | "succeeded" | "failed" | "skipped";

export type RunNode = {
  name: string;
  label: string;
  status: NodeStatus;
};

export type RunOutputs = {
  reference_image: string | null;
  reference_images?: string[] | null;
  optimized_image: string | null;
  model_glb: string | null;
  model_stl: string | null;
};

export type RunStatus = "pending" | "running" | "awaiting_image" | "awaiting_mesh" | "succeeded" | "failed";

export type RunMode = "auto" | "confirm";

export type CaptureCandidate = {
  key: string;
  label: string;
  url: string;
  default_selected: boolean;
};

export type CaptureRecord = {
  capture_id: string;
  status: string;
  step_label?: string | null;
  candidates?: CaptureCandidate[] | Record<string, string | Partial<CaptureCandidate>> | null;
  error?: string | { message?: string } | null;
};

export type UploadRunSource = {
  kind: "upload";
  images: File[];
};

export type CameraRunSource = {
  kind: "camera";
  captureId: string;
  selectedKeys: string[];
};

export type RunSource = UploadRunSource | CameraRunSource;

export type RunSummary = {
  run_id: string;
  status: RunStatus;
  created_at: string | null;
  prompt: string;
  current_label: string | null;
  reference_image: string | null;
};

export type RunRecord = {
  run_id: string;
  workflow_id: string;
  status: RunStatus;
  created_at?: string;
  current_node: string | null;
  nodes: RunNode[];
  inputs: { prompt: string; style: string | null; image_url: string | null; mode?: RunMode };
  artifacts: {
    lux3d_stage?: string;
    lux3d_status_label?: string;
    lux3d_task_id?: number;
    lux3d_elapsed_seconds?: number;
    optimize_image_started_at?: string;
    optimize_image_elapsed_seconds?: number;
    image_prompt?: string;
    poll_mesh_started_at?: string;
    poll_mesh_elapsed_seconds?: number;
  };
  outputs: RunOutputs;
  error: { code: string; message: string } | null;
};
