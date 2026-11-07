import { useEffect, useState } from 'react';
import { Icon } from '../components/ui';
import { SLIDES, slideSrc, slideSrcSet } from './slides';

const reduced = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Auto-advancing photo carousel with 3D service icon. Pauses on hover/focus; static with reduced motion. */
export function VisualCarousel({ compact = false }: { compact?: boolean }) {
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const [failed, setFailed] = useState<Record<string, boolean>>({});
  useEffect(() => {
    if (paused || reduced()) return;
    const t = setInterval(() => setI((x) => (x + 1) % SLIDES.length), 3800);
    return () => clearInterval(t);
  }, [paused]);
  const s = SLIDES[i]!;
  return (
    <section className={`visual ${compact ? 'visual--compact' : ''}`} aria-roledescription="carousel" aria-label="What you can do on Click"
      onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      {SLIDES.map((sl, idx) => (
        <div key={sl.key} className={`visual__slide ${idx === i ? 'is-active' : ''}`} style={{ background: sl.tint }} aria-hidden={idx !== i}>
          {!failed[sl.key] && (
            <img src={slideSrc(sl.key, 640)} srcSet={slideSrcSet(sl.key)} sizes="(min-width: 900px) 55vw, 100vw" alt={idx === i ? sl.alt : ''}
              loading={idx < 2 ? 'eager' : 'lazy'} decoding="async" onError={() => setFailed((f) => ({ ...f, [sl.key]: true }))} />
          )}
        </div>
      ))}
      <div className="visual__shade" />
      <div className="visual__caption" aria-live="polite">
        <span className="icon3d" data-tile={s.tile}><Icon name={s.icon} size={compact ? 20 : 24} /></span>
        <span><strong>{s.title}</strong><span>{s.caption}</span></span>
      </div>
      <div className="visual__dots" role="tablist" aria-label="Choose slide">
        {SLIDES.map((sl, idx) => (
          <button key={sl.key} role="tab" aria-selected={idx === i} aria-label={sl.title} onClick={() => { setI(idx); setPaused(true); }} />
        ))}
      </div>
    </section>
  );
}
