export default function Skeleton({
  className = "",
  count = 1,
}: {
  className?: string;
  count?: number;
}) {
  // Renders each placeholder as a direct sibling (a Fragment, not a
  // wrapping <div>) — a wrapper here was the actual bug behind the
  // "one giant grey rectangle" look: it made the whole group a SINGLE
  // child of whatever grid/flex layout the caller used, so the parent's
  // gap/columns never applied to the individual placeholders, and they
  // stacked with zero spacing between them.
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={`skeleton ${className}`}
          // Staggers BOTH animations defined on .skeleton (shimmer +
          // entrance fade, see index.css) so a group of cards visibly
          // cascades in rather than popping in as one static block.
          style={{ animationDelay: `${i * 60}ms` }}
          aria-hidden="true"
        />
      ))}
    </>
  );
}
