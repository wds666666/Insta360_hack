type Props = {
  title: string;
  note: string;
  src?: string | null;
  srcs?: string[];
  empty: string;
};

export function ImagePanel({ title, note, src, srcs, empty }: Props) {
  const frames = srcs && srcs.length > 0 ? srcs : src ? [src] : [];
  const multiple = frames.length > 1;
  return (
    <figure className={multiple ? "image-panel has-gallery" : "image-panel"}>
      <figcaption>
        <span className="panel-title">
          <strong>{title}</strong>
          {multiple ? <span className="image-count">{frames.length} 个视角</span> : null}
        </span>
        <span className="panel-note">{note}</span>
      </figcaption>
      {multiple ? (
        <div className="image-strip">
          {frames.map((frame, index) => (
            <div className="image-frame" key={frame}>
              <img src={frame} alt={`${title}，视角 ${index + 1}`} loading="lazy" />
              <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
            </div>
          ))}
        </div>
      ) : frames.length === 1 ? (
        <img src={frames[0]} alt={title} loading="lazy" />
      ) : (
        <p className="muted">{empty}</p>
      )}
    </figure>
  );
}
