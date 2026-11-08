/**
 * The Click logo. Geometry and colours are fixed brand assets: the violet
 * rounded mark, white ring and mint centre never change with an app's theme.
 * Only the wordmark colour adapts to the background (`tone`).
 */
export const CLICK_BRAND = { mark: '#5B3DF5', ring: '#FFFFFF', dot: '#14C8A0' } as const;

export function ClickMark({ size = 28, title }: { size?: number; title?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role={title ? 'img' : undefined} aria-label={title} aria-hidden={title ? undefined : true}>
      <rect width="32" height="32" rx="9" fill={CLICK_BRAND.mark} />
      <circle cx="16" cy="16" r="7.5" fill="none" stroke={CLICK_BRAND.ring} strokeWidth="3" />
      <circle cx="16" cy="16" r="2.6" fill={CLICK_BRAND.dot} />
    </svg>
  );
}

export interface LogoProps {
  /** `light` = on light surfaces (dark wordmark); `dark` = on dark surfaces (white wordmark). */
  tone?: 'light' | 'dark';
  size?: number;
  /** Product name shown beside the logo, e.g. "Partner". It is a label, not part of the logo. */
  product?: string;
  className?: string;
}

export function Logo({ tone = 'light', size = 28, product, className = '' }: LogoProps) {
  return (
    <span className={`logo click-logo click-logo--${tone} ${className}`} aria-label={product ? `Click ${product}` : 'Click'} role="img">
      <ClickMark size={size} />
      <span className="click-logo__word" aria-hidden="true" style={{ fontSize: size * 0.8 }}>click</span>
      {product && <span className="click-logo__product" aria-hidden="true">{product}</span>}
    </span>
  );
}
