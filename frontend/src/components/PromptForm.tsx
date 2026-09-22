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

const MAX_REFERENCES = 8;

const DEFAULT_BRIEF = `你在看同一间房的参考图，可能是一张全景，也可能还有行星图或其他角度。请只写一段给图像模型的中文提示词，不要解释。
画面必须是这一间房的 3D 屋剖面：斜俯视等距视角，只选一个最能看清内部的角度，墙被切开，里面的空间一眼能读懂。不要把不同视角画成好几间房。
严格依据照片里真实的墙、地面、门窗和主要家具，不要另造房间。
最后这张图会交给 Lux3D 做成可打印的模型。家具画成贴地的粗实心块。去掉床品褶皱、灯线、画框、植物、门把手和细桌腿，细过一根手指的东西不要出现。表面平整，少纹理。`;

type Props = {
  disabled: boolean;
  onImages: (files: File[]) => void;
  onSubmit: (prompt: string, images: File[], mode: "auto" | "confirm") => void;
};

export function PromptForm({ disabled, onImages, onSubmit }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const filesRef = useRef(files);
  filesRef.current = files;
  const [dragging, setDragging] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [mode, setMode] = useState<"auto" | "confirm">("confirm");

  const onImagesRef = useRef(onImages);
  onImagesRef.current = onImages;

  function add(incoming: File[]) {
    if (!incoming.length) {
      return;
    }
    const accepted = incoming.filter((file) => isPanorama(file));
    if (!accepted.length) {
      setFormError("参考图只支持 jpg、png、webp");
      return;
    }
    const room = MAX_REFERENCES - filesRef.current.length;
    const next = [...filesRef.current, ...accepted.slice(0, Math.max(room, 0))];
    if (accepted.length < incoming.length) {
      setFormError("参考图只支持 jpg、png、webp");
    } else if (accepted.length > room) {
      setFormError(`参考图最多 ${MAX_REFERENCES} 张`);
    } else {
      setFormError(null);
    }
    filesRef.current = next;
    setFiles(next);
    onImagesRef.current(next);
  }

  function remove(index: number) {
    const next = filesRef.current.filter((_, item) => item !== index);
    filesRef.current = next;
    setFormError(null);
    setFiles(next);
    onImagesRef.current(next);
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
      add(image ? [image] : []);
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
        if (!files.length) {
          setFormError("先放入至少一张参考图");
          return;
        }
        if (!prompt) {
          setFormError("写一下要摸到的墙、地面和家具");
          return;
        }
        setFormError(null);
        onSubmit(prompt, files, mode);
      }}
    >
      <div className="field">
        <span id="panorama-label">参考图</span>
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
            add(Array.from(event.dataTransfer.files));
          }}
        >
          <input
            ref={input}
            className="file-input"
            name="image"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            multiple
            disabled={disabled}
            aria-labelledby="panorama-label"
            onChange={(event) => {
              add(Array.from(event.currentTarget.files ?? []));
              event.currentTarget.value = "";
            }}
          />
          <button
            className="file-button"
            type="button"
            disabled={disabled}
            onClick={() => input.current?.click()}
          >
            {files.length ? "再加参考图" : "选择参考图"}
          </button>
          <span className={files.length ? "file-name is-set" : "file-name"}>
            {files.length
              ? `已选 ${files.length} 张`
              : "全景、行星或其他视角。可多选，也可拖入或粘贴"}
          </span>
          {files.length ? (
            <ul className="file-list">
              {files.map((item, index) => (
                <li className="file-chip" key={`${item.name}-${item.size}-${item.lastModified}-${index}`}>
                  <span>{item.name}</span>
                  <button type="button" disabled={disabled} onClick={() => remove(index)} aria-label={`移除${item.name}`}>
                    移除
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
      <div className="mode" role="radiogroup" aria-label="生成方式">
        <span className="mode-label">生成方式</span>
        <div className="mode-options">
          <button
            className={mode === "confirm" ? "mode-option is-selected" : "mode-option"}
            type="button"
            role="radio"
            aria-checked={mode === "confirm"}
            disabled={disabled}
            onClick={() => setMode("confirm")}
          >
            <strong>分步确认</strong>
            <span>先看剖面说明，再决定出图和做模型</span>
          </button>
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
        </div>
      </div>
      <label className="field">
        <span>给 DeepSeek 的说明</span>
        <textarea
          name="prompt"
          disabled={disabled}
          rows={8}
          defaultValue={DEFAULT_BRIEF}
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
