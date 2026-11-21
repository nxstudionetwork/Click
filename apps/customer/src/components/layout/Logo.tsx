/**
 * Click. brand lockup for the Customer App: the supplied glossy app icon (assets/Glossy Click App Logo.png,
 * cropped without stretching into public/brand/) and the "Click." wordmark. The period takes the amber of the
 * logo's dot. Never recolour or distort the icon.
 */
export function Logo({ size = 32, wordmark = true }: { size?: number; wordmark?: boolean }) {
  return (
    <span className="brand" role="img" aria-label="Click.">
      <img
        className="brand__icon" src="/brand/click-icon-96.png" srcSet="/brand/click-icon-96.png 1x, /brand/click-icon-192.png 2x"
        width={size} height={size} alt="" decoding="async"
      />
      {wordmark && <span className="brand__word" aria-hidden="true" style={{ fontSize: size * 0.72 }}>Click<span className="brand__dot">.</span></span>}
    </span>
  );
}
