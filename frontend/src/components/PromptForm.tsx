import { useEffect, useRef, useState } from "react";

function isPanorama(file: File): boolean {
  return /^image\/(jpeg|png|webp)$/.test(file.type) || /\.(jpe?g|png|webp)$/i.test(file.name);
}

function imageFromClipboard(data: DataTransfer | null): File | null {
  if (!data) {
    return null;
  }
  for (const file of data.files) {
    if (file.type.startsWith("image/") || isPanorama(file)) {
      return namePasted(file);
    }
  }
  for (const item of data.items) {
    if (item.kind === "file" && item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (file) {
        return namePasted(file);
      }
    }
  }
  return null;
}

function namePasted(file: File): File {
  if (file.name && !/^image\.(png|jpe?g|webp)$/i.test(file.name)) {
    return file;
  }
  const ext = file.type === "image/jpeg" ? "jpg" : file.type === "image/webp" ? "webp" : "png";
  return new File([file], `已粘贴的全景.${ext}`, { type: file.type || "image/png" });
}

type Props = {
  disabled: boolean;
  onImage: (file: File | null) => void;
  onSubmit: (prompt: string, image: File, mode: "auto" | "confirm") => void;
};

export function PromptForm({ disabled, onImage, onSubmit }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [mode, setMode] = useState<"auto" | "confirm">("auto");

  const onImageRef = useRef(onImage);
  onImageRef.current = onImage;

  function choose(next: File | null) {
    if (next && !isPanorama(next)) {
      setFormError("全景只支持 jpg、png、webp");
      return;
    }
    setFormError(null);
    setFile(next);
    onImageRef.current(next);
  }

  useEffect(() => {
    if (disabled) {
      return;
    }
    const onPaste = (event: ClipboardEvent) => {
      const image = imageFromClipboard(event.clipboardData);
      if (!image) {
        return;
      }
      event.preventDefault();
      choose(image);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [disabled]);

  return (
    <form
      className="form"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const prompt = String(data.get("prompt") ?? "").trim();
        if (!file) {
          setFormError("先选择一张全景");
          return;
        }
        if (!prompt) {
          setFormError("写一下要摸到的墙、地面和家具");
          return;
        }
        setFormError(null);
        onSubmit(prompt, file, mode);
      }}
    >
      <div className="field">
        <span id="panorama-label">全景图</span>
        <div
          className={dragging ? "file-pick is-drag" : "file-pick"}
          onDragOver={(event) => {
            event.preventDefault();
            if (!disabled) {
              setDragging(true);
            }
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            if (disabled) {
              return;
            }
            choose(event.dataTransfer.files[0] ?? null);
          }}
        >
          <input
            ref={input}
            className="file-input"
            name="image"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            disabled={disabled}
            aria-labelledby="panorama-label"
            onChange={(event) => {
              choose(event.currentTarget.files?.[0] ?? null);
              event.currentTarget.value = "";
            }}
          />
          <button
            className="file-button"
            type="button"
            disabled={disabled}
            onClick={() => input.current?.click()}
          >
            {file ? "更换全景" : "选择全景"}
          </button>
          <span className={file ? "file-name is-set" : "file-name"}>
            {file ? file.name : "拖到这里，或按 Ctrl+V / ⌘V 粘贴"}
          </span>
        </div>
      </div>
      <div className="mode" role="radiogroup" aria-label="生成方式">
        <span className="mode-label">生成方式</span>
        <div className="mode-options">
          <button
            className={mode === "auto" ? "mode-option is-selected" : "mode-option"}
            type="button"
            role="radio"
            aria-checked={mode === "auto"}
            disabled={disabled}
            onClick={() => setMode("auto")}
          >
            <strong>全自动</strong>
            <span>提交后直接生成模型</span>
          </button>
          <button
            className={mode === "confirm" ? "mode-option is-selected" : "mode-option"}
            type="button"
            role="radio"
            aria-checked={mode === "confirm"}
            disabled={disabled}
            onClick={() => setMode("confirm")}
          >
            <strong>先看优化图</strong>
            <span>确认后再做模型</span>
          </button>
        </div>
      </div>
      <label className="field">
        <span>空间说明</span>
        <textarea
          name="prompt"
          disabled={disabled}
          rows={7}
          placeholder="写下要摸到的墙、地面和家具。人物、灯具和文字不要留。"
        />
      </label>
      {formError ? (
        <p className="error" role="alert">
          {formError}
        </p>
      ) : null}
      <button className="submit" type="submit" disabled={disabled}>
        {disabled ? "正在生成触觉地图" : "生成触觉地图"}
      </button>
    </form>
  );
}
