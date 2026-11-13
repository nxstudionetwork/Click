import { useEffect, useRef, type ReactNode } from 'react';

/** Accessible bottom sheet (mobile) / centered dialog (desktop). */
export function Sheet({ open, onClose, label, children, variant = 'auto' }: { open: boolean; onClose: () => void; label: string; children: ReactNode; variant?: 'auto' | 'full' }) {
  const ref = useRef<HTMLDivElement>(null);
  // Callers usually pass an inline onClose; keep the latest in a ref so the effect runs only when the sheet opens or
  // closes (re-running it on every render moved focus back to the dialog while the customer was typing in it).
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && close.current();
    document.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
      prev?.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="sheet-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`sheet ${variant === 'full' ? 'sheet--full' : ''}`} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1} ref={ref}>
        {children}
      </div>
    </div>
  );
}
