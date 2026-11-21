import { Fragment, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Icon, TextArea, TextField, useToast } from '@click/ui';
import { apiMessage, home } from '../lib/api';
import { useAccess } from '../session/access';
import { useOS, useOSSession, CONTEXT_KEY } from '../session/OSSession';
import { Alert, Dialog } from './ui';

/** Location context. Only shown when the person may view more than one location; changing it refreshes Home. */
export function ContextSwitcher() {
  const ctx = useOS();
  const { refetchContext } = useOSSession();
  const qc = useQueryClient();
  const toast = useToast();
  const opts = ctx.contextOptions;
  const set = useMutation({
    mutationFn: (id: string | null) => home.setContext(id),
    onSuccess: () => {
      refetchContext();
      void qc.invalidateQueries({ queryKey: ['os', 'home'] });
      void qc.invalidateQueries({ queryKey: ['os', 'widget'] });
      void qc.invalidateQueries({ queryKey: CONTEXT_KEY });
    },
    onError: (e) => toast(apiMessage(e), 'error'),
  });
  if (!opts?.switchable) {
    return (
      <span className="header__org" title="Your organization and location">
        <Icon name="building" size={16} />{ctx.organization.name}
        {ctx.orgContext.location && <span className="muted">· {ctx.orgContext.location.name}</span>}
      </span>
    );
  }
  return (
    <label className="header__org" style={{ padding: '0 6px 0 10px' }}>
      <Icon name="building" size={16} /><span>{ctx.organization.name}</span>
      <span className="sr-only">Location context</span>
      <select value={opts.selected ?? ''} onChange={(e) => set.mutate(e.target.value || null)} disabled={set.isPending}
              style={{ border: 0, background: 'transparent', color: 'inherit', font: 'inherit', maxWidth: 200 }}>
        <option value="">{opts.orgWide ? 'All locations' : 'All my locations'}</option>
        {opts.units.map((u) => <option key={u.id} value={u.id}>{'  '.repeat(Math.max(0, u.depth))}{u.name} · {u.typeLabel}</option>)}
      </select>
    </label>
  );
}

export function HelpMenu() {
  const access = useAccess();
  const [open, setOpen] = useState(false);
  const [dialog, setDialog] = useState<'none' | 'shortcuts' | 'report'>('none');
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);
  useEffect(() => {
    const h = (e: Event) => setDialog((e as CustomEvent).detail);
    window.addEventListener('os:dialog', h);
    return () => window.removeEventListener('os:dialog', h);
  }, []);
  const item = (label: string, icon: Parameters<typeof Icon>[0]['name'], onClick: () => void) => (
    <button className="menu-item" role="menuitem" onClick={() => { setOpen(false); onClick(); }}><Icon name={icon} size={16} />{label}</button>
  );
  const nav = useNavigate();
  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <button className="icon-btn" aria-label="Help" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}><Icon name="help" size={19} /></button>
      {open && (
        <div className="popover" role="menu">
          {item('Business OS help', 'book', () => nav('/help'))}
          {item('Search help', 'search', () => window.dispatchEvent(new CustomEvent('os:palette')))}
          {item('Keyboard shortcuts', 'key', () => setDialog('shortcuts'))}
          {item('Contact support', 'send', () => nav('/help#support'))}
          {item('Report a problem', 'alert', () => setDialog('report'))}
          {access.can('system.health.view') && item('System status', 'settings', () => nav('/settings/system'))}
        </div>
      )}
      {dialog === 'shortcuts' && <ShortcutsDialog onClose={() => setDialog('none')} />}
      {dialog === 'report' && <ReportDialog onClose={() => setDialog('none')} />}
    </div>
  );
}

export const SHORTCUTS: [string, string][] = [
  ['Ctrl / ⌘ + K', 'Search and run commands'], ['?', 'Show keyboard shortcuts'], ['G then H', 'Go to Home'], ['G then A', 'Go to Approvals'],
  ['G then T', 'Go to Tasks'], ['G then N', 'Go to Notifications'], ['G then P', 'Go to People & HR'], ['Esc', 'Close a dialog or panel'],
];

function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  return (
    <Dialog title="Keyboard shortcuts" onClose={onClose}>
      <div className="kbd-list">{SHORTCUTS.map(([k, d]) => <Fragment key={k}><kbd>{k}</kbd><span>{d}</span></Fragment>)}</div>
    </Dialog>
  );
}

function ReportDialog({ onClose }: { onClose: () => void }) {
  const loc = useLocation();
  const [summary, setSummary] = useState('');
  const [details, setDetails] = useState('');
  const send = useMutation({ mutationFn: () => home.reportProblem({ summary, details, page: loc.pathname }) });
  return (
    <Dialog title="Report a problem" onClose={onClose} footer={send.data ? <Button onClick={onClose}>Done</Button> : <>
      <Button variant="outline" onClick={onClose}>Cancel</Button>
      <Button loading={send.isPending} disabled={summary.trim().length < 5} onClick={() => send.mutate()}>Send report</Button>
    </>}>
      {send.data ? (
        <Alert tone="success">Thanks — your report <strong>{send.data.reference}</strong> {send.data.routed ? 'was sent to the Business OS administrators.' : 'was recorded.'}
          {send.data.supportEmail && <> You can also email <a href={`mailto:${send.data.supportEmail}`}>{send.data.supportEmail}</a>.</>}</Alert>
      ) : (
        <>
          {send.error && <Alert tone="error">{apiMessage(send.error)}</Alert>}
          <TextField label="What went wrong?" value={summary} onChange={(e) => setSummary(e.target.value)} maxLength={150} />
          <TextArea label="Details (optional)" value={details} onChange={(e) => setDetails(e.target.value)} maxLength={2000} />
          <p className="xs muted">We include the page you’re on ({loc.pathname}). Don’t include passwords or personal data.</p>
        </>
      )}
    </Dialog>
  );
}

/** Global shortcuts: "?" for help, "g" + key to jump. Ignored while typing in a field. */
export function useShortcuts() {
  const nav = useNavigate();
  useEffect(() => {
    let g = 0;
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === '?') { window.dispatchEvent(new CustomEvent('os:dialog', { detail: 'shortcuts' })); return; }
      if (e.key.toLowerCase() === 'g') { g = Date.now(); return; }
      if (Date.now() - g < 1200) {
        const to = { h: '/home', a: '/approvals', t: '/tasks', n: '/notifications', p: '/people' }[e.key.toLowerCase()];
        if (to) { e.preventDefault(); nav(to); }
        g = 0;
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [nav]);
}

