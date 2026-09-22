type Props = {
  title: string;
  note: string;
  src?: string | null;
  srcs?: string[];
  empty: string;
};

export function ImagePanel({ title, note, src, srcs, empty }: Props) {
  const frames = srcs && srcs.length > 0 ? srcs : src ? [src] : [];
  return (
    <figure className="image-panel">
      <figcaption>
        {title}
        <span>{note}</span>
      </figcaption>
      {frames.length > 1 ? (
        <div className="image-strip">
          {frames.map((frame) => (
            <img key={frame} src={frame} alt={title} />
          ))}
        </div>
      ) : frames.length === 1 ? (
        <img src={frames[0]} alt={title} />
      ) : (
        <p className="muted">{empty}</p>
      )}
    </figure>
  );
}
