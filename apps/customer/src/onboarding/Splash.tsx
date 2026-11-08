import { useEffect, useState } from 'react';
import { SLIDES, slideSrc } from './slides';

const KEY = 'click.splashShown';
export const splashAlreadyShown = () => { try { return sessionStorage.getItem(KEY) === '1'; } catch { return true; } };

/**
 * Cold-start splash: logo reveal over a mosaic of the Click ecosystem, then fades out.
 * ~2.4s (0.8s with reduced motion), once per browser session. Images fall back to brand tints.
 */
export function Splash({ onDone }: { onDone: () => void }) {
  const reduce = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const [leaving, setLeaving] = useState(false);
  useEffect(() => {
    try { sessionStorage.setItem(KEY, '1'); } catch { /* ignore */ }
    const total = reduce ? 800 : 2400;
    const t1 = setTimeout(() => setLeaving(true), total - 350);
    const t2 = setTimeout(onDone, total);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [onDone, reduce]);

  return (
    <div className={`splash ${leaving ? 'splash--out' : ''}`} role="status" aria-label="Loading Click">
      <div className="splash__mosaic" aria-hidden="true">
        {SLIDES.map((s, i) => (
          <div key={s.key} className="splash__tile" style={{ background: s.tint, animationDelay: `${i * 90}ms` }}>
            <img src={slideSrc(s.key, 640)} alt="" decoding="async" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
          </div>
        ))}
      </div>
      <div className="splash__veil" />
      <div className="splash__center">
        <div className="splash__mark">
          <svg viewBox="0 0 32 32" aria-hidden="true">
            <rect width="32" height="32" rx="9" fill="var(--c-brand)" />
            <circle cx="16" cy="16" r="7.5" fill="none" stroke="#fff" strokeWidth="3" />
            <circle cx="16" cy="16" r="2.6" fill="var(--c-accent)" />
          </svg>
        </div>
        <div className="splash__word">click</div>
        <p className="splash__tag">Everything you need. One Click away.</p>
        <div className="splash__bar"><span /></div>
      </div>
    </div>
  );
}
