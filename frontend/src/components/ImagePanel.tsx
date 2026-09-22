type Props = {
  title: string;
  note: string;
  src: string | null;
  empty: string;
};

export function ImagePanel({ title, note, src, empty }: Props) {
  return (
    <figure className="image-panel">
      <figcaption>
        {title}
        <span>{note}</span>
      </figcaption>
      {src ? <img src={src} alt={title} /> : <p className="muted">{empty}</p>}
    </figure>
  );
}
