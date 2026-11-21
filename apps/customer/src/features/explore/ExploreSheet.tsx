import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Icon } from '../../components/ui';
import { ExploreContent } from './ExploreContent';

const EXIT_MS = 240;

/**
 * Explore as a premium bottom sheet (about 80% of the screen), opened from the bottom navigation.
 * The page behind stays visible, blurred and dimmed. Scrolls internally; closes on Escape, backdrop tap,
 * the close button, the drag handle, any navigation, or a route change.
 */
export function ExploreSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [mounted, setMounted] = useState(open);
  const [leaving, setLeaving] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const { pathname } = useLocation();

  useEffect(() => {
    if (open) { setMounted(true); setLeaving(false); return; }
    if (!mounted) return;
    setLeaving(true);
    const t = setTimeout(() => { setMounted(false); setLeaving(false); }, EXIT_MS);
    return () => clearTimeout(t);
  }, [open, mounted]);

  // Close when the route changes (e.g. a tile was tapped).
  const first = useRef(true);
  useEffect(() => { if (first.current) { first.current = false; return; } onClose(); }, [pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = overflow; prev?.focus?.(); };
  }, [open, onClose]);

  if (!mounted) return null;
  return (
    <div className={`xsheet-backdrop ${leaving ? 'is-leaving' : ''}`} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={panel} className="xsheet" role="dialog" aria-modal="true" aria-labelledby="explore-sheet-h" tabIndex={-1} data-theme="explore">
        <div className="xsheet__bar">
          <button type="button" className="xsheet__handle" aria-label="Close Explore" onClick={onClose}><span /></button>
          <button type="button" className="icon-btn xsheet__close" aria-label="Close Explore" onClick={onClose}><Icon name="close" /></button>
        </div>
        <div className="xsheet__body">
          <ExploreContent titleId="explore-sheet-h" onNavigate={onClose} />
        </div>
      </div>
    </div>
  );
}
