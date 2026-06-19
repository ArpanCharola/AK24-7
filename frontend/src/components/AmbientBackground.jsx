/* Global ambient background: two fixed, decorative, non-interactive layers that
   sit behind the page content (the content wrapper must be `relative z-10`).
   Styling lives in index.css (.aurora-bg + .aurora-grid). Drop this as the first
   child of a page's outermost container. */
export default function AmbientBackground() {
  return (
    <>
      <div className="aurora-bg" aria-hidden="true" />
      <div className="aurora-grid" aria-hidden="true" />
    </>
  );
}
