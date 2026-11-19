/**
 * Business OS building blocks shared by every page (and every future module). Primitives that are the same across
 * Click apps (Button, TextField, Icon, Empty/Error states, Skeleton, Toast) come from @click/ui.
 */
import { useEffect, useId, useRef, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Button, EmptyState, ErrorState, Icon, Skeleton, type IconName } from '@click/ui';
import { ApiError } from '@click/api';
import { initials } from '../lib/format';

export function PageHeader({ title, description, crumbs, actions }: {
  title: ReactNode; description?: ReactNode; crumbs?: { label: string; to?: string }[]; actions?: ReactNode;
}) {
  useEffect(() => {
    if (typeof title === 'string') document.title = `${title} · Click Business OS`;
  }, [title]);
  return (
    <div className="page-head">
      <div className="page-head__text">
        {crumbs && crumbs.length > 0 && (
          <nav className="crumbs" aria-label="Breadcrumb">
            {crumbs.map((c, i) => (
              <span key={i} className="row" style={{ gap: 6 }}>
                {c.to ? <Link to={c.to}>{c.label}</Link> : <span>{c.label}</span>}
                {i < crumbs.length - 1 && <span aria-hidden="true">/</span>}
              </span>
            ))}
          </nav>
        )}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="row row--wrap">{actions}</div>}
    </div>
  );
}

export function Card({ title, actions, children, foot, flush, className = '' }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; foot?: ReactNode; flush?: boolean; className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card__head">
          {typeof title === 'string' ? <h2>{title}</h2> : title}
          {actions && <div className="row">{actions}</div>}
        </header>
      )}
      <div className={`card__body ${flush ? 'card__body--flush' : ''}`}>{children}</div>
      {foot && <footer className="card__foot">{foot}</footer>}
    </section>
  );
}

type Tone = 'success' | 'warning' | 'danger' | 'info' | 'brand' | 'neutral';
const STATUS_TONE: Record<string, Tone> = {
  active: 'success', approved: 'success', done: 'success', ok: 'success', connected: 'success', success: 'success',
  pending: 'warning', invited: 'info', in_progress: 'info', open: 'brand', warning: 'warning', not_configured: 'neutral',
  rejected: 'danger', suspended: 'danger', error: 'danger', failure: 'danger', denied: 'danger', cancelled: 'neutral',
  deactivated: 'neutral', waiting: 'neutral', skipped: 'neutral', urgent: 'danger', high: 'warning', normal: 'neutral', low: 'neutral',
};

export function Status({ value, label, tone }: { value: string; label?: string; tone?: Tone }) {
  const t = tone ?? STATUS_TONE[value] ?? 'neutral';
  return <span className={`status ${t !== 'neutral' ? `status--${t}` : ''}`}>{label ?? value.replace(/_/g, ' ')}</span>;
}

export function Avatar({ name, src, size }: { name?: string | null; src?: string | null; size?: 'sm' | 'lg' }) {
  return (
    <span className={`avatar ${size ? `avatar--${size}` : ''}`} aria-hidden="true">
      {src ? <img src={src} alt="" /> : initials(name)}
    </span>
  );
}

export function Alert({ tone = 'info', children, icon }: { tone?: 'info' | 'error' | 'warning' | 'success'; children: ReactNode; icon?: IconName }) {
  return (
    <div className={`alert alert--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon name={icon ?? (tone === 'success' ? 'check' : tone === 'info' ? 'help' : 'alert')} size={16} />
      <div>{children}</div>
    </div>
  );
}

function useEscape(onClose: () => void) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);
}

function useFocusFirst<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const el = ref.current?.querySelector<HTMLElement>('input, select, textarea, button:not([data-close])') ?? ref.current;
    el?.focus();
    return () => prev?.focus?.();
  }, []);
  return ref;
}

export function Dialog({ title, onClose, children, footer, wide }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  useEscape(onClose);
  const ref = useFocusFirst<HTMLDivElement>();
  const id = useId();
  return (
    <div className="overlay overlay--center" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`dialog ${wide ? 'dialog--wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={id} ref={ref} tabIndex={-1}>
        <div className="dialog__head">
          <h2 id={id} className="grow">{title}</h2>
          <button className="icon-btn" data-close onClick={onClose} aria-label="Close"><Icon name="close" size={18} /></button>
        </div>
        <div className="dialog__body">{children}</div>
        {footer && <div className="dialog__foot">{footer}</div>}
      </div>
    </div>
  );
}

export function Drawer({ title, onClose, children, footer }: { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  useEscape(onClose);
  const ref = useFocusFirst<HTMLDivElement>();
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="drawer" role="dialog" aria-modal="true" ref={ref} tabIndex={-1}>
        <div className="drawer__head">
          <div className="grow"><h2>{title}</h2></div>
          <button className="icon-btn" data-close onClick={onClose} aria-label="Close"><Icon name="close" size={18} /></button>
        </div>
        <div className="drawer__body">{children}</div>
        {footer && <div className="drawer__foot">{footer}</div>}
      </aside>
    </div>
  );
}

export function ConfirmDialog({ title, message, confirmLabel, danger, busy, onConfirm, onClose, children }: {
  title: string; message: ReactNode; confirmLabel: string; danger?: boolean; busy?: boolean; onConfirm: () => void; onClose: () => void; children?: ReactNode;
}) {
  return (
    <Dialog title={title} onClose={onClose} footer={<>
      <Button variant="outline" onClick={onClose}>Cancel</Button>
      <Button variant={danger ? 'danger' : 'primary'} loading={busy} onClick={onConfirm}>{confirmLabel}</Button>
    </>}>
      <p className="muted">{message}</p>
      {children}
    </Dialog>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: string; count?: number }[] }) {
  return (
    <div className="tabs" role="tablist">
      {items.map((it) => (
        <button key={it.value} role="tab" aria-selected={value === it.value} className="tab" onClick={() => onChange(it.value)}>
          {it.label}{it.count !== undefined && <span className="tab__count">{it.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function LoadingRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="loader" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} height={18} width={`${90 - i * 12}%`} />)}
    </div>
  );
}

export function PageLoader({ label = 'Loading' }: { label?: string }) {
  return <div className="page-state" aria-busy="true"><div className="stack" style={{ alignItems: 'center' }}><span className="btn__spinner" style={{ color: 'var(--c-brand)', width: 22, height: 22 }} /><span className="muted small">{label}…</span></div></div>;
}

/** Turns any API failure into the right state: permission denied, needs MFA, not found, offline, or generic. */
export function QueryError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (error instanceof ApiError) {
    if (error.code === 'mfa_required') return <MfaNeeded />;
    if (error.status === 403) return <Forbidden message={error.message} />;
    if (error.status === 404) return <EmptyState icon="search" title="Not found" message="It may have been removed, or you don’t have access to it." />;
  }
  return <ErrorState error={error} onRetry={onRetry} />;
}

export function Forbidden({ message }: { message?: string }) {
  return (
    <div className="state state--warning" role="alert">
      <div className="state__icon"><Icon name="lock" /></div>
      <h3>You don’t have access to this</h3>
      <p>{message ?? 'Your role doesn’t include this area. If you need it for your work, ask your manager or a Business OS administrator.'}</p>
      <Link to="/home">Back to Home</Link>
    </div>
  );
}

export function MfaNeeded() {
  return (
    <div className="state state--warning" role="alert">
      <div className="state__icon"><Icon name="shield" /></div>
      <h3>Two-step verification required</h3>
      <p>This area holds sensitive information. Turn on two-step verification to use it.</p>
      <Link to="/settings/security">Set up two-step verification</Link>
    </div>
  );
}

export function Empty({ icon = 'inbox', title, message, action }: { icon?: IconName; title: string; message?: string; action?: ReactNode }) {
  return <EmptyState icon={icon} title={title} message={message} action={action} />;
}

export function Pager({ page, hasNext, count, onPage }: { page: number; hasNext: boolean; count: number; onPage: (p: number) => void }) {
  if (page === 1 && !hasNext) return null;
  return (
    <div className="pager">
      <span>{count} total</span>
      <div className="row">
        <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <span>Page {page}</span>
        <Button size="sm" variant="outline" disabled={!hasNext} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </div>
  );
}

export function Field({ label, hint, error, children, htmlFor }: { label: string; hint?: string; error?: string; children: ReactNode; htmlFor?: string }) {
  return (
    <div className={`field ${error ? 'field--error' : ''}`}>
      <label className="field__label" htmlFor={htmlFor}>{label}</label>
      {children}
      {error ? <span className="field__error">{error}</span> : hint && <span className="field__hint">{hint}</span>}
    </div>
  );
}
